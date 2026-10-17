"""Cash-market volume anomalies from the snapshot's daily bars.

A volume spike is a day whose traded quantity stands far above the symbol's own
recent norm. The maths is a pure function over two wide frames — daily volumes
and (optionally) daily closes — so it is unit-tested with no network, and the
Due Diligence page reads the ``volumes`` and ``prices`` snapshot datasets
straight into it.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

VOLUME_COLUMNS = [
    "Symbol",
    "Volume",
    "Average volume",
    "Ratio",
    "Z-score",
    "Return",
    "Turnover",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=VOLUME_COLUMNS)


def volume_anomalies(
    volumes: pd.DataFrame,
    closes: Optional[pd.DataFrame] = None,
    lookback: int = 20,
    threshold: float = 3.0,
    min_turnover: float = 1e7,
) -> pd.DataFrame:
    """Symbols whose latest session traded ``threshold`` times their recent norm.

    ``volumes`` is a wide frame (index ``Date``, one column per symbol); the last
    row is the session under test and the ``lookback`` rows before it are the
    baseline. ``closes``, when given, adds the session return and the rupee
    turnover, and ``min_turnover`` drops illiquid names whose spike is a rounding
    error. Rows are ordered by the volume ratio, heaviest first.
    """
    if volumes is None or volumes.empty:
        return _empty()

    frame = volumes.sort_index().apply(pd.to_numeric, errors="coerce")
    if len(frame) < 2:
        return _empty()

    latest = frame.iloc[-1]
    history = frame.iloc[:-1].tail(max(int(lookback), 1))

    average = history.mean()
    deviation = history.std(ddof=0)
    table = pd.DataFrame(
        {
            "Volume": latest,
            "Average volume": average,
            "Ratio": latest / average.replace(0, np.nan),
            "Z-score": (latest - average) / deviation.replace(0, np.nan),
        }
    )
    table = table[table["Ratio"] >= threshold]
    if table.empty:
        return _empty()

    table["Return"] = np.nan
    table["Turnover"] = np.nan

    if closes is not None and not closes.empty:
        prices = closes.sort_index().apply(pd.to_numeric, errors="coerce")
        close = prices.iloc[-1].reindex(table.index)
        previous = (
            prices.iloc[-2].reindex(table.index)
            if len(prices) >= 2
            else pd.Series(np.nan, index=table.index)
        )
        table["Return"] = close / previous.replace(0, np.nan) - 1
        table["Turnover"] = table["Volume"] * close

    if min_turnover and table["Turnover"].notna().any():
        table = table[table["Turnover"].fillna(0) >= min_turnover]
        if table.empty:
            return _empty()

    table.index.name = "Symbol"
    return (
        table.reset_index()
        .sort_values("Ratio", ascending=False)
        .reset_index(drop=True)[VOLUME_COLUMNS]
    )


__all__ = ["VOLUME_COLUMNS", "volume_anomalies"]
