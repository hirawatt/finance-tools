"""Rule-based red-flag detection over per-symbol fundamentals.

Rules are declarative and pure: each takes a single symbol's fundamentals row
and reports whether it trips. :func:`detect_red_flags` turns a company-data
frame into a tidy list of flags; :func:`flag_summary` condenses it per holding.

Thresholds were calibrated against Yahoo Finance data for NSE stocks (note that
``debtToEquity`` is reported as a percentage, so 200 means 2x).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import pandas as pd

from utils.market_data import FUNDAMENTAL_FIELDS, RISK_FIELDS

# Column labels (shared with the fetch layer).
_PE = FUNDAMENTAL_FIELDS["trailingPE"]
_PB = FUNDAMENTAL_FIELDS["priceToBook"]
_DEBT = RISK_FIELDS["debtToEquity"]
_CURRENT_RATIO = RISK_FIELDS["currentRatio"]
_PROFIT_MARGIN = RISK_FIELDS["profitMargins"]
_OPERATING_MARGIN = RISK_FIELDS["operatingMargins"]
_REVENUE_GROWTH = RISK_FIELDS["revenueGrowth"]
_EARNINGS_GROWTH = RISK_FIELDS["earningsGrowth"]
_FREE_CASH_FLOW = RISK_FIELDS["freeCashflow"]
_NET_INCOME = RISK_FIELDS["netIncomeToCommon"]

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class RedFlagRule:
    """A single red-flag rule: when ``predicate`` holds, ``detail`` explains it."""

    name: str
    severity: str
    predicate: Callable[[pd.Series], bool]
    detail: Callable[[pd.Series], str]


def _num(row: pd.Series, column: str) -> Optional[float]:
    """Read a numeric field, treating missing/NaN/non-numeric as ``None``."""
    if column not in row:
        return None
    value = row[column]
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


# --- Individual rule predicates -------------------------------------------------

def _is_loss_making(row: pd.Series) -> bool:
    net_income = _num(row, _NET_INCOME)
    pe = _num(row, _PE)
    margin = _num(row, _PROFIT_MARGIN)
    return (
        (net_income is not None and net_income < 0)
        or (pe is not None and pe <= 0)
        or (margin is not None and margin < 0)
    )


DEFAULT_RULES: Sequence[RedFlagRule] = (
    RedFlagRule(
        "Loss-making",
        "high",
        _is_loss_making,
        lambda row: (
            f"Net loss of ₹{abs(_num(row, _NET_INCOME)) / 1e7:,.1f} cr"
            if (_num(row, _NET_INCOME) or 0) < 0
            else "Negative profit margin"
        ),
    ),
    RedFlagRule(
        "Negative book value",
        "high",
        lambda row: (_num(row, _PB) or 0) < 0,
        lambda row: f"P/B {_num(row, _PB):.2f}",
    ),
    RedFlagRule(
        "High leverage",
        "high",
        lambda row: (_num(row, _DEBT) or 0) > 200,
        lambda row: f"Debt/equity {_num(row, _DEBT):.0f}%",
    ),
    RedFlagRule(
        "Elevated leverage",
        "medium",
        lambda row: 100 < (_num(row, _DEBT) or 0) <= 200,
        lambda row: f"Debt/equity {_num(row, _DEBT):.0f}%",
    ),
    RedFlagRule(
        "Negative free cash flow",
        "medium",
        lambda row: (_num(row, _FREE_CASH_FLOW) or 0) < 0,
        lambda row: f"FCF ₹{_num(row, _FREE_CASH_FLOW) / 1e7:,.1f} cr",
    ),
    RedFlagRule(
        "Falling revenue",
        "medium",
        lambda row: (_num(row, _REVENUE_GROWTH) or 0) < 0,
        lambda row: f"Revenue {_num(row, _REVENUE_GROWTH):+.1%}",
    ),
    RedFlagRule(
        "Falling earnings",
        "medium",
        lambda row: (_num(row, _EARNINGS_GROWTH) or 0) < 0,
        lambda row: f"Earnings {_num(row, _EARNINGS_GROWTH):+.1%}",
    ),
    RedFlagRule(
        "Weak liquidity",
        "medium",
        lambda row: (_num(row, _CURRENT_RATIO) or math.inf) < 1,
        lambda row: f"Current ratio {_num(row, _CURRENT_RATIO):.2f}",
    ),
    RedFlagRule(
        "Operating losses",
        "medium",
        lambda row: (_num(row, _OPERATING_MARGIN) or 0) < 0,
        lambda row: f"Operating margin {_num(row, _OPERATING_MARGIN):+.1%}",
    ),
    RedFlagRule(
        "Stretched valuation",
        "low",
        lambda row: (_num(row, _PE) or 0) > 60,
        lambda row: f"P/E {_num(row, _PE):.1f}",
    ),
)

FLAG_COLUMNS = ["Symbol", "Flag", "Severity", "Detail"]


def detect_red_flags(
    company_data: pd.DataFrame, rules: Sequence[RedFlagRule] = DEFAULT_RULES
) -> pd.DataFrame:
    """Evaluate ``rules`` against every row of ``company_data``.

    Returns a tidy frame with one row per (symbol, flag), ordered by severity.
    """
    if company_data is None or company_data.empty:
        return pd.DataFrame(columns=FLAG_COLUMNS)

    rows = []
    for symbol, row in company_data.iterrows():
        for rule in rules:
            if rule.predicate(row):
                rows.append(
                    {
                        "Symbol": symbol,
                        "Flag": rule.name,
                        "Severity": rule.severity,
                        "Detail": rule.detail(row),
                    }
                )

    flags = pd.DataFrame(rows, columns=FLAG_COLUMNS)
    if flags.empty:
        return flags
    order = flags["Severity"].map(SEVERITY_ORDER)
    return flags.assign(_order=order).sort_values(["_order", "Symbol"]).drop(
        columns="_order"
    ).reset_index(drop=True)


def flag_summary(flags: pd.DataFrame) -> pd.DataFrame:
    """One row per flagged holding: worst severity, flag count and the flags."""
    if flags is None or flags.empty:
        return pd.DataFrame(columns=["Flags", "Worst severity", "Details"])

    grouped = flags.groupby("Symbol")
    summary = pd.DataFrame(
        {
            "Flags": grouped.size(),
            "Worst severity": grouped["Severity"].apply(
                lambda severities: min(severities, key=SEVERITY_ORDER.get)
            ),
            "Details": grouped["Flag"].apply(lambda names: ", ".join(names)),
        }
    )
    order = summary["Worst severity"].map(SEVERITY_ORDER)
    return summary.assign(_order=order).sort_values(
        ["_order", "Flags"], ascending=[True, False]
    ).drop(columns="_order")
