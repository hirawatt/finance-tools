"""Default-risk screening via the Altman Z-score.

Classic Altman Z for listed companies::

    Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5
    X1 = working capital / total assets
    X2 = retained earnings / total assets
    X3 = EBIT / total assets
    X4 = market value of equity / total liabilities
    X5 = revenue / total assets

Zones: Z ≥ 2.99 safe, 1.81–2.99 grey, < 1.81 distress.

Extraction and scoring are pure; only :func:`fetch_default_risk` touches the
network (Yahoo Finance statements).
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from utils.concurrency import parallel_map
from utils.market_data import to_ticker

# Balance-sheet / income-statement line items, with fallbacks for the varying
# labels Yahoo uses across issuers and sectors.
TOTAL_ASSETS = ("Total Assets",)
CURRENT_ASSETS = ("Current Assets",)
CURRENT_LIABILITIES = ("Current Liabilities",)
WORKING_CAPITAL = ("Working Capital",)
RETAINED_EARNINGS = ("Retained Earnings",)
TOTAL_LIABILITIES = ("Total Liabilities Net Minority Interest", "Total Liabilities")
EBIT = ("EBIT", "Operating Income", "EBITDA")
REVENUE = ("Total Revenue", "Operating Revenue")

INPUT_FIELDS = [
    "total_assets",
    "working_capital",
    "retained_earnings",
    "ebit",
    "total_liabilities",
    "revenue",
]


def _latest(frame: Optional[pd.DataFrame], names: Iterable[str]) -> Optional[float]:
    """Most recent non-null value for the first matching line item.

    Statement columns are period-end dates; they are sorted newest-first so the
    result does not depend on the order the source happens to use.
    """
    if frame is None or frame.empty:
        return None

    try:
        ordered = frame[sorted(frame.columns, reverse=True)]
    except TypeError:  # non-comparable column labels
        ordered = frame

    for name in names:
        if name in ordered.index:
            series = ordered.loc[name].dropna()
            if not series.empty:
                try:
                    return float(series.iloc[0])
                except (TypeError, ValueError):
                    continue
    return None


def extract_z_inputs(
    balance_sheet: Optional[pd.DataFrame], income_stmt: Optional[pd.DataFrame]
) -> dict:
    """Pull the Altman Z-score inputs from a company's statements."""
    current_assets = _latest(balance_sheet, CURRENT_ASSETS)
    current_liabilities = _latest(balance_sheet, CURRENT_LIABILITIES)
    working_capital = _latest(balance_sheet, WORKING_CAPITAL)
    if working_capital is None and current_assets is not None and current_liabilities is not None:
        working_capital = current_assets - current_liabilities

    return {
        "total_assets": _latest(balance_sheet, TOTAL_ASSETS),
        "working_capital": working_capital,
        "retained_earnings": _latest(balance_sheet, RETAINED_EARNINGS),
        "total_liabilities": _latest(balance_sheet, TOTAL_LIABILITIES),
        "ebit": _latest(income_stmt, EBIT),
        "revenue": _latest(income_stmt, REVENUE),
    }


def altman_z_score(inputs: dict, market_cap: Optional[float]) -> Optional[float]:
    """Compute the Altman Z-score, or ``None`` when inputs are missing."""
    total_assets = inputs.get("total_assets")
    total_liabilities = inputs.get("total_liabilities")
    if not total_assets or total_assets <= 0 or not total_liabilities or not market_cap:
        return None

    required = (
        inputs.get("working_capital"),
        inputs.get("retained_earnings"),
        inputs.get("ebit"),
        inputs.get("revenue"),
    )
    if any(value is None for value in required):
        return None

    x1 = inputs["working_capital"] / total_assets
    x2 = inputs["retained_earnings"] / total_assets
    x3 = inputs["ebit"] / total_assets
    x4 = market_cap / total_liabilities
    x5 = inputs["revenue"] / total_assets
    return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5


def classify_z(z: Optional[float]) -> Optional[str]:
    """Map a Z-score to its Altman zone."""
    if z is None:
        return None
    if z >= 2.99:
        return "Safe"
    if z >= 1.81:
        return "Grey"
    return "Distress"


def fetch_default_risk(
    symbols: Iterable[str], market_caps: Optional[pd.Series] = None
) -> pd.DataFrame:
    """Fetch statements and compute Altman Z-scores per symbol.

    ``market_caps`` is a Series indexed by symbol (e.g. from the fundamentals
    fetch); without it X4 cannot be computed and the score is omitted.
    """
    import yfinance as yf

    market_caps = market_caps if market_caps is not None else pd.Series(dtype=float)
    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]

    def _statement_inputs(symbol: str) -> dict:
        ticker = yf.Ticker(to_ticker(symbol))
        try:
            balance_sheet = ticker.balance_sheet
        except Exception:
            balance_sheet = None
        try:
            income_stmt = ticker.income_stmt
        except Exception:
            income_stmt = None
        return extract_z_inputs(balance_sheet, income_stmt)

    rows = {}
    for symbol, inputs, _error in parallel_map(_statement_inputs, clean):
        # A symbol whose statements could not be fetched has no inputs; score it
        # as missing rather than dropping the row, so coverage stays visible.
        if inputs is None:
            inputs = extract_z_inputs(None, None)

        score = altman_z_score(inputs, market_caps.get(symbol))
        rows[symbol] = {
            "Z-score": score,
            "Zone": classify_z(score),
            "Total assets": inputs.get("total_assets"),
            "Total liabilities": inputs.get("total_liabilities"),
            "EBIT": inputs.get("ebit"),
        }

    frame = pd.DataFrame.from_dict(
        rows,
        orient="index",
        columns=["Z-score", "Zone", "Total assets", "Total liabilities", "EBIT"],
    )
    frame.index.name = "Symbol"
    return frame
