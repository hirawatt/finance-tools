"""Market-data access and portfolio analytics for the Co-Pilot.

The code is split into two groups:

* Pure analytics helpers (:func:`to_ticker`, :func:`compute_returns`,
  :func:`correlation_matrix`, :func:`compute_beta`,
  :func:`weighted_portfolio_returns`, :func:`performance_summary`) that operate
  on plain pandas objects with no network or Streamlit dependency, so they can
  be unit-tested in isolation.
* :func:`fetch_price_history`, which pulls daily adjusted closes from Yahoo
  Finance (via ``yfinance``) for a list of NSE symbols plus a benchmark index.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# NSE symbols are suffixed on Yahoo Finance, e.g. POLYCAB -> POLYCAB.NS
NSE_SUFFIX = ".NS"
DEFAULT_BENCHMARK = "^NSEI"  # NIFTY 50
BENCHMARK_NAME = "NIFTY 50"

# Minimum overlapping daily observations before we trust a beta/statistic.
MIN_OBSERVATIONS = 20

# Fundamental fields pulled per symbol for the valuation view, mapped from the
# Yahoo Finance ``info`` keys to display labels.
FUNDAMENTAL_FIELDS = {
    "trailingPE": "P/E (trailing)",
    "forwardPE": "P/E (forward)",
    "priceToBook": "P/B",
    "trailingEps": "EPS (trailing)",
    "dividendYield": "Dividend yield (%)",
    "marketCap": "Market cap",
}

# Metrics surfaced in the headline performance summary. Percentage-style
# metrics are noted so the UI can format them consistently.
PERCENT_METRICS = {
    "Cumulative Return",
    "CAGR",
    "Volatility (ann.)",
    "Max Drawdown",
    "Value at Risk (95%)",
}


def to_ticker(symbol: str) -> str:
    """Map an NSE symbol to its Yahoo Finance ticker.

    Symbols that are already explicit (an index such as ``^NSEI`` or a fully
    qualified ticker containing a dot) are passed through untouched.
    """
    symbol = str(symbol).strip().upper()
    if not symbol or symbol.startswith("^") or "." in symbol:
        return symbol
    return f"{symbol}{NSE_SUFFIX}"


def _extract_close(data: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    """Normalise the result of ``yfinance.download`` into a close-price frame.

    Depending on the number of tickers, yfinance returns either a flat frame
    (single ticker) or a ``(field, ticker)`` MultiIndex frame.
    """
    if data is None or len(data) == 0:
        return pd.DataFrame()

    columns = data.columns
    if isinstance(columns, pd.MultiIndex):
        level0 = set(columns.get_level_values(0))
        level1 = set(columns.get_level_values(1))
        if "Close" in level0:
            return data["Close"]
        if "Close" in level1:
            return data.xs("Close", axis=1, level=1)
        return pd.DataFrame()

    if "Close" not in columns:
        return pd.DataFrame()
    close = data[["Close"]].copy()
    close.columns = [tickers[0] if tickers else "Close"]
    return close


def fetch_price_history(
    symbols: Iterable[str],
    period: str = "1y",
    benchmark: Optional[str] = DEFAULT_BENCHMARK,
) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Fetch daily adjusted close prices for ``symbols`` and ``benchmark``.

    Returns a ``(prices, benchmark)`` tuple where ``prices`` has one column per
    resolved symbol and ``benchmark`` is the benchmark close series (or ``None``
    when unavailable). Symbols without data are silently dropped so callers can
    decide what to do about them.
    """
    import yfinance as yf

    # De-duplicate while preserving order.
    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]
    tickers = [to_ticker(s) for s in clean]
    downloads = tickers + ([benchmark] if benchmark else [])

    if not downloads:
        return pd.DataFrame(), None

    data = yf.download(
        downloads,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    close = _extract_close(data, downloads)
    if close.empty:
        return pd.DataFrame(), None

    # Keep only symbols that actually returned data, mapped back to NSE codes.
    resolved = {ticker: symbol for ticker, symbol in zip(tickers, clean)}
    present = [t for t in tickers if t in close.columns]
    prices = close[present].rename(columns=resolved)
    prices = prices.loc[:, prices.notna().any(axis="index")]

    benchmark_series = None
    if benchmark and benchmark in close.columns:
        benchmark_series = close[benchmark].dropna()
        benchmark_series.name = BENCHMARK_NAME

    return prices, benchmark_series


def fetch_fundamentals(symbols: Iterable[str]) -> pd.DataFrame:
    """Fetch valuation fundamentals (P/E, P/B, EPS, ...) for ``symbols``.

    Returns a DataFrame indexed by symbol with one column per entry in
    :data:`FUNDAMENTAL_FIELDS`. Symbols that fail to resolve are omitted, so a
    single bad ticker never breaks the whole table.
    """
    import yfinance as yf

    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]
    rows = {}
    for symbol in clean:
        try:
            info = yf.Ticker(to_ticker(symbol)).info
        except Exception:
            continue
        if not isinstance(info, dict) or not info:
            continue
        rows[symbol] = {label: info.get(key) for key, label in FUNDAMENTAL_FIELDS.items()}

    frame = pd.DataFrame.from_dict(
        rows, orient="index", columns=list(FUNDAMENTAL_FIELDS.values())
    )
    frame.index.name = "Symbol"
    return frame


def compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily simple returns from a price frame (one column per symbol)."""
    if prices is None or prices.empty:
        return pd.DataFrame()
    returns = prices.sort_index().pct_change(fill_method=None)
    return returns.dropna(how="all")


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlation of daily returns."""
    if returns is None or returns.empty:
        return pd.DataFrame()
    return returns.corr()


def compute_beta(returns: pd.DataFrame, benchmark: pd.Series) -> pd.Series:
    """Beta of each column's returns against the benchmark's returns.

    Beta is ``cov(asset, benchmark) / var(benchmark)``. Symbols with fewer than
    :data:`MIN_OBSERVATIONS` overlapping observations are skipped.
    """
    if returns is None or returns.empty or benchmark is None or benchmark.empty:
        return pd.Series(dtype=float)

    joined = returns.join(benchmark.rename("__benchmark__"), how="inner")
    benchmark_var = joined["__benchmark__"].var()
    if not benchmark_var or np.isnan(benchmark_var):
        return pd.Series(dtype=float)

    betas = {}
    for column in returns.columns:
        pair = joined[[column, "__benchmark__"]].dropna()
        if len(pair) < MIN_OBSERVATIONS:
            continue
        betas[column] = pair[column].cov(pair["__benchmark__"]) / benchmark_var

    if not betas:
        return pd.Series(dtype=float)
    return pd.Series(betas, name="Beta").sort_values(ascending=False)


def weighted_portfolio_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Value-weighted portfolio returns.

    ``weights`` is indexed by symbol; it is renormalised over the columns that
    actually have return data so partial coverage still works.
    """
    if returns is None or returns.empty or weights is None or weights.empty:
        return pd.Series(dtype=float)

    aligned = weights.reindex(returns.columns).fillna(0.0)
    total = aligned.sum()
    if total == 0:
        return pd.Series(dtype=float)

    normalised = aligned / total
    return returns.mul(normalised, axis="columns").sum(axis="columns")


def weighted_average_pe(pe: pd.Series, weights: pd.Series) -> Optional[float]:
    """Value-weighted portfolio P/E.

    The aggregate P/E of a portfolio is total value divided by total earnings,
    which is the value-weighted *harmonic* mean of the individual P/Es (not the
    arithmetic mean). Holdings with a non-positive P/E (loss-making) are
    excluded. Returns ``None`` when no usable P/E is available.
    """
    if pe is None or pe.empty or weights is None or weights.empty:
        return None

    joined = pd.concat([pe.rename("pe"), weights.rename("weight")], axis=1).dropna()
    joined = joined[joined["pe"] > 0]
    total = joined["weight"].sum()
    if joined.empty or total == 0:
        return None

    normalised = joined["weight"] / total
    return float(1.0 / (normalised / joined["pe"]).sum())


def performance_summary(returns: pd.Series) -> pd.Series:
    """Headline risk/return metrics for a returns series, via quantstats.

    Returns a Series indexed by metric label. Metrics that cannot be computed
    (e.g. from a near-empty series) are reported as ``NaN`` rather than raising.
    """
    import quantstats as qs

    metrics = [
        ("Cumulative Return", qs.stats.comp),
        ("CAGR", qs.stats.cagr),
        ("Volatility (ann.)", qs.stats.volatility),
        ("Sharpe", qs.stats.sharpe),
        ("Sortino", qs.stats.sortino),
        ("Calmar", qs.stats.calmar),
        ("Max Drawdown", qs.stats.max_drawdown),
        ("Value at Risk (95%)", qs.stats.var),
    ]

    if returns is None or len(returns.dropna()) < 2:
        return pd.Series({label: np.nan for label, _ in metrics}, name="Portfolio")

    values = {}
    for label, func in metrics:
        try:
            values[label] = float(func(returns))
        except (ValueError, ZeroDivisionError, TypeError):
            values[label] = np.nan
    return pd.Series(values, name="Portfolio")


def full_metrics_report(returns: pd.Series) -> pd.DataFrame:
    """The complete quantstats tearsheet metrics table (basic mode)."""
    import quantstats as qs

    if returns is None or len(returns.dropna()) < 2:
        return pd.DataFrame()
    return qs.reports.metrics(returns, mode="basic", display=False)
