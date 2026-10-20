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

from utils.concurrency import parallel_map, retry_call

# NSE symbols are suffixed on Yahoo Finance, e.g. POLYCAB -> POLYCAB.NS
NSE_SUFFIX = ".NS"
DEFAULT_BENCHMARK = "^NSEI"  # NIFTY 50
BENCHMARK_NAME = "NIFTY 50"

# Companies that changed their NSE ticker: the curated watchlists and older
# holdings exports still use the left-hand code, while Yahoo only knows the
# right-hand one. Frames are still keyed by the requested code (see `_tidy`),
# so the rest of the app keeps the spelling it already stores. A ticker with an
# exchange suffix is used as-is: a few names (e.g. Panasonic Energy) are only
# quoted on the BSE.
SYMBOL_ALIASES = {
    "ADANITRANS": "ADANIENSOL",
    "AMARAJABAT": "ARE&M",
    "BAJAJAUTO": "BAJAJ-AUTO",
    "GMRINFRA": "GMRAIRPORT",
    "IIFLSEC": "IIFLCAPS",
    "IIFLWAM": "360ONE",
    "MAXVIL": "MAXESTATES",
    "MCDOWELL-N": "UNITDSPR",
    "MCDOWELL_N": "UNITDSPR",
    "MICEL-T": "MICEL",
    "ORISSAMINE6": "ORISSAMINE",
    "PANAENERG": "PANAENERG.BO",
    "RASIELEC-X": "RASIELEC.BO",
    "ZOMATO": "ETERNAL",
}

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

# Additional fields used by the red-flag rules.
RISK_FIELDS = {
    "debtToEquity": "Debt to equity (%)",
    "currentRatio": "Current ratio",
    "profitMargins": "Profit margin",
    "operatingMargins": "Operating margin",
    "revenueGrowth": "Revenue growth",
    "earningsGrowth": "Earnings growth",
    "freeCashflow": "Free cash flow",
    "netIncomeToCommon": "Net income",
}

# Everything pulled from ``yfinance`` in one pass, keyed by the info field.
COMPANY_FIELDS = {**FUNDAMENTAL_FIELDS, **RISK_FIELDS}

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
    qualified ticker containing a dot) are passed through untouched. Tickers a
    company has since changed are resolved through :data:`SYMBOL_ALIASES`.
    """
    symbol = str(symbol).strip().upper()
    if not symbol or symbol.startswith("^") or "." in symbol:
        return symbol
    symbol = SYMBOL_ALIASES.get(symbol, symbol)
    return symbol if "." in symbol else f"{symbol}{NSE_SUFFIX}"


def _extract_field(
    data: pd.DataFrame, tickers: Sequence[str], field: str = "Close"
) -> pd.DataFrame:
    """Normalise a ``yfinance.download`` result into one field's frame.

    Depending on the number of tickers, yfinance returns either a flat frame
    (single ticker) or a ``(field, ticker)`` MultiIndex frame.
    """
    if data is None or len(data) == 0:
        return pd.DataFrame()

    columns = data.columns
    if isinstance(columns, pd.MultiIndex):
        level0 = set(columns.get_level_values(0))
        level1 = set(columns.get_level_values(1))
        if field in level0:
            return data[field]
        if field in level1:
            return data.xs(field, axis=1, level=1)
        return pd.DataFrame()

    if field not in columns:
        return pd.DataFrame()
    extracted = data[[field]].copy()
    extracted.columns = [tickers[0] if tickers else field]
    return extracted


def _extract_close(data: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    """The close-price frame from a ``yfinance.download`` result."""
    return _extract_field(data, tickers, "Close")


def _download(downloads: Sequence[str], period: str) -> pd.DataFrame:
    """One Yahoo download for every ticker, with the project's retry policy."""
    import yfinance as yf

    return retry_call(
        lambda: yf.download(
            list(downloads),
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    )


def _tidy(extracted: pd.DataFrame, tickers: Sequence[str], clean: Sequence[str]) -> pd.DataFrame:
    """Keep symbols that returned data, mapped back from tickers to NSE codes."""
    if extracted is None or extracted.empty:
        return pd.DataFrame()

    # One ticker can serve more than one requested code (an alias, or a broker
    # suffix variant), so build the frame column by column rather than assuming
    # a one-to-one rename.
    columns = [
        extracted[ticker].rename(symbol)
        for ticker, symbol in zip(tickers, clean)
        if ticker in extracted.columns
    ]
    if not columns:
        return pd.DataFrame()

    wide = pd.concat(columns, axis=1)
    return wide.loc[:, wide.notna().any(axis="index")]


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
    # De-duplicate while preserving order.
    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]
    tickers = [to_ticker(s) for s in clean]
    downloads = list(dict.fromkeys(tickers + ([benchmark] if benchmark else [])))

    if not downloads:
        return pd.DataFrame(), None

    close = _extract_field(_download(downloads, period), downloads, "Close")
    if close.empty:
        return pd.DataFrame(), None

    prices = _tidy(close, tickers, clean)

    benchmark_series = None
    if benchmark and benchmark in close.columns:
        benchmark_series = close[benchmark].dropna()
        benchmark_series.name = BENCHMARK_NAME

    return prices, benchmark_series


def fetch_price_and_volume_history(
    symbols: Iterable[str],
    period: str = "1y",
    benchmark: Optional[str] = DEFAULT_BENCHMARK,
) -> Tuple[pd.DataFrame, Optional[pd.Series], pd.DataFrame]:
    """Closes, the benchmark and traded volume from a single Yahoo download.

    The nightly snapshot wants both prices and volumes; pulling them in one pass
    keeps the upstream request count down. Returns ``(prices, benchmark,
    volumes)`` where ``volumes`` has one column per resolved symbol (the
    benchmark, an index, is dropped as it carries no traded volume).
    """
    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]
    tickers = [to_ticker(s) for s in clean]
    downloads = list(dict.fromkeys(tickers + ([benchmark] if benchmark else [])))

    if not downloads:
        return pd.DataFrame(), None, pd.DataFrame()

    data = _download(downloads, period)
    close = _extract_field(data, downloads, "Close")
    prices = _tidy(close, tickers, clean)

    benchmark_series = None
    if benchmark and not close.empty and benchmark in close.columns:
        benchmark_series = close[benchmark].dropna()
        benchmark_series.name = BENCHMARK_NAME

    volume = _extract_field(data, downloads, "Volume")
    volumes = _tidy(volume, tickers, clean)

    return prices, benchmark_series, volumes


def fetch_company_data(
    symbols: Iterable[str], fields: dict = COMPANY_FIELDS
) -> pd.DataFrame:
    """Fetch labelled fundamentals for ``symbols`` in one pass.

    Returns a DataFrame indexed by symbol with one column per display label in
    ``fields``. Symbols that fail to resolve are omitted, so a single bad ticker
    never breaks the whole table.

    Yahoo's quote endpoint is per-symbol, so the requests are fanned out over a
    bounded thread pool (with retries) instead of run one after another.
    """
    import yfinance as yf

    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]
    labels = list(dict.fromkeys(fields.values()))

    def _info(symbol: str) -> dict:
        return yf.Ticker(to_ticker(symbol)).info

    rows = {}
    for symbol, info, error in parallel_map(_info, clean):
        if error is not None or not isinstance(info, dict) or not info:
            continue
        rows[symbol] = {label: info.get(key) for key, label in fields.items()}

    frame = pd.DataFrame.from_dict(rows, orient="index", columns=labels)
    frame.index.name = "Symbol"
    return frame


def fetch_fundamentals(symbols: Iterable[str]) -> pd.DataFrame:
    """Valuation fields only (thin wrapper over :func:`fetch_company_data`)."""
    return fetch_company_data(symbols, FUNDAMENTAL_FIELDS)


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
    if joined.empty:
        return pd.Series(dtype=float)

    bench = joined["__benchmark__"]
    benchmark_var = bench.var()
    if not benchmark_var or np.isnan(benchmark_var):
        return pd.Series(dtype=float)

    # ``DataFrame.cov`` drops NaNs pairwise, exactly like the per-column
    # ``Series.cov`` loop it replaces, so the covariance lookup is one operation
    # instead of one pass per holding.
    covariances = joined.cov()["__benchmark__"]

    # Overlap is counted on the rows the benchmark actually has, matching the
    # pairwise dropna the covariance uses.
    overlap = joined.loc[bench.notna()].notna().sum()
    usable = [c for c in returns.columns if overlap.get(c, 0) >= MIN_OBSERVATIONS]
    if not usable:
        return pd.Series(dtype=float)

    betas = (covariances.loc[usable] / benchmark_var).dropna()
    if betas.empty:
        return pd.Series(dtype=float)
    return betas.rename("Beta").sort_values(ascending=False)


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
