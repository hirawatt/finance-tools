"""Pairs that have drifted apart: same-industry candidates and a spread z-score.

Two stocks that usually move together make a useful relative-value screen when
their spread stretches. This module picks candidate pairs from the committed
sector master and scores each one with a log-price hedge ratio and the z-score
of the latest spread — pure functions over a wide price frame, no network.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

PAIR_COLUMNS = [
    "Symbol A",
    "Symbol B",
    "Industry",
    "Beta",
    "Correlation",
    "Spread z",
    "Spread",
    "Signal",
]

# Below this many overlapping observations a pair's statistics are not trusted.
MIN_OBSERVATIONS = 30


def candidate_pairs(
    sectors: pd.DataFrame,
    symbols: Optional[Iterable[str]] = None,
) -> List[Tuple[str, str, str]]:
    """Every same-industry pair in ``sectors``, optionally limited to ``symbols``.

    ``sectors`` is the committed master (``data/stock-sector.csv``), whose symbol
    column is ``NSE code`` (or ``Symbol`` if already renamed). Pairs are returned
    as ``(symbol_a, symbol_b, industry)`` with the two symbols sorted.
    """
    if sectors is None or sectors.empty or "Industry" not in sectors.columns:
        return []

    column = next(
        (name for name in ("Symbol", "NSE code") if name in sectors.columns), None
    )
    if column is None:
        return []

    universe = (
        {str(value).strip().upper() for value in symbols}
        if symbols is not None
        else None
    )

    pairs: List[Tuple[str, str, str]] = []
    for industry, group in sectors.dropna(subset=["Industry"]).groupby("Industry"):
        names = sorted(
            {str(value).strip().upper() for value in group[column] if str(value).strip()}
        )
        if universe is not None:
            names = [name for name in names if name in universe]
        for index, first in enumerate(names):
            for second in names[index + 1 :]:
                pairs.append((first, second, industry))
    return pairs


def hedge_ratio(prices: pd.DataFrame, a: str, b: str) -> float:
    """OLS slope of ``log a`` on ``log b`` over their overlapping history."""
    if a not in prices.columns or b not in prices.columns:
        return np.nan
    joined = prices[[a, b]].dropna()
    if len(joined) < 2:
        return np.nan
    x = np.log(joined[b].astype(float))
    y = np.log(joined[a].astype(float))
    variance = x.var()
    if not variance or np.isnan(variance):
        return np.nan
    return float(np.cov(y, x)[0, 1] / variance)


def spread_zscore(
    prices: pd.DataFrame, a: str, b: str, lookback: int = 60
) -> Optional[dict]:
    """Latest z-score of the log spread ``log a - beta * log b``.

    Returns ``None`` when there is not enough history, the spread is degenerate,
    or the two symbols are not correlated enough to compare. ``Symbol A`` rich
    means the spread is above its own mean (A looks expensive against B).
    """
    if a not in prices.columns or b not in prices.columns:
        return None

    joined = prices[[a, b]].dropna()
    if len(joined) < MIN_OBSERVATIONS:
        return None

    beta = hedge_ratio(joined, a, b)
    if not np.isfinite(beta):
        return None

    spread = np.log(joined[a].astype(float)) - beta * np.log(joined[b].astype(float))
    window = spread.tail(max(int(lookback), MIN_OBSERVATIONS))
    deviation = window.std()
    if not deviation or np.isnan(deviation):
        return None

    z_score = (spread.iloc[-1] - window.mean()) / deviation
    returns = joined.pct_change(fill_method=None).dropna()
    if len(returns) < MIN_OBSERVATIONS:
        return None
    correlation = returns[a].corr(returns[b])
    if not np.isfinite(correlation):
        return None

    return {
        "Symbol A": a,
        "Symbol B": b,
        "Beta": float(beta),
        "Correlation": float(correlation),
        "Spread z": float(z_score),
        "Spread": float(spread.iloc[-1]),
        "Signal": "A rich vs B" if z_score > 0 else "A cheap vs B",
    }


def rank_pairs(
    prices: pd.DataFrame,
    pairs: Sequence[Tuple[str, str, str]],
    lookback: int = 60,
    threshold: float = 2.0,
    min_correlation: float = 0.5,
) -> pd.DataFrame:
    """Score candidate pairs and keep the ones whose spread is stretched.

    A pair qualifies when its return correlation is at least ``min_correlation``
    and the latest spread z-score is at least ``threshold`` in absolute value;
    the result is ordered by how stretched the spread is.
    """
    rows = []
    for a, b, industry in pairs:
        stats = spread_zscore(prices, a, b, lookback=lookback)
        if stats is None:
            continue
        if abs(stats["Correlation"]) < min_correlation:
            continue
        stats["Industry"] = industry
        rows.append(stats)

    if not rows:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    frame = pd.DataFrame(rows)
    frame = frame[frame["Spread z"].abs() >= threshold]
    if frame.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    order = frame["Spread z"].abs().sort_values(ascending=False).index
    return frame.reindex(order)[PAIR_COLUMNS].reset_index(drop=True)


__all__ = [
    "MIN_OBSERVATIONS",
    "PAIR_COLUMNS",
    "candidate_pairs",
    "hedge_ratio",
    "rank_pairs",
    "spread_zscore",
]
