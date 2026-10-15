"""Monte Carlo price/value projections.

A deliberately simple geometric Brownian motion projection: estimate the drift
and volatility of a daily-returns sample, simulate many paths, and return the
percentile bands. This is a scenario range, not a prediction.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

DEFAULT_QUANTILES = (5, 25, 50, 75, 95)


def forecast_paths(
    returns: pd.Series,
    start_value: float,
    horizon: int = 21,
    simulations: int = 1000,
    seed: int = 0,
    quantiles: Sequence[float] = DEFAULT_QUANTILES,
) -> pd.DataFrame:
    """Project ``start_value`` forward ``horizon`` steps from a returns sample.

    Returns a frame indexed by step (0 = today) with one column per quantile
    (``P5``, ``P25``, ...). The same ``seed`` yields the same frame.
    """
    if returns is None:
        return pd.DataFrame()

    sample = pd.Series(returns).dropna()
    if len(sample) < 2 or horizon <= 0 or simulations <= 0:
        return pd.DataFrame()

    mu = float(sample.mean())
    sigma = float(sample.std())
    drift = mu - 0.5 * sigma**2

    rng = np.random.default_rng(seed)
    shocks = rng.normal(drift, sigma, size=(simulations, horizon))
    paths = start_value * np.exp(np.cumsum(shocks, axis=1))

    bands = np.percentile(paths, quantiles, axis=0).T  # (horizon, len(quantiles))
    frame = pd.DataFrame(
        bands,
        index=np.arange(1, horizon + 1),
        columns=[f"P{q:g}" for q in quantiles],
    )
    start_row = pd.DataFrame(
        {column: [start_value] for column in frame.columns}, index=[0]
    )
    frame = pd.concat([start_row, frame])
    frame.index.name = "Step"
    return frame
