"""NSE F&O end-of-day option data: the bhavcopy, put-call parity and OI surges.

The nightly job downloads NSE's UDiFF F&O bhavcopy and stores it through
:func:`parse_fo_bhavcopy` as one row per (underlying, expiry, strike) with the
call and put side by side, so parity reads straight across a row. Everything the
Due Diligence page needs — implied forwards, parity breaks, strikes with fresh
positioning — is a pure function over that frame.

Only :func:`fetch_fo_bhavcopy` (and its latest-day wrapper) touch the network,
and neither is called from the page: the app reads the snapshot.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from utils.concurrency import retry_call

# NSE publishes one bhavcopy per trading day under a date-stamped URL.
BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_{day}_F_0000.csv.zip"
)

# The index underlyings whose options are European, so put-call parity holds
# cleanly. Stock options are American-style and only approximate it.
INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50")

OPTION_TYPES = ("CE", "PE")

# Index and stock futures, whose close is the true forward for its expiry and
# the natural reference for put-call parity.
FUTURES_TYPES = ("IDF", "STF")

# The per-strike EOD chain: one row per (Symbol, Expiry, Strike), with the call
# and put side of that strike on the same row. ``Future close`` repeats across
# the strikes of an expiry (and is blank when no future traded that day).
OPTION_COLUMNS = [
    "Date",
    "Symbol",
    "Expiry",
    "Strike",
    "Underlying price",
    "Future close",
    "CE Close",
    "PE Close",
    "CE OI",
    "PE OI",
    "CE OI change",
    "PE OI change",
    "CE Volume",
    "PE Volume",
]

# Raw bhavcopy column -> the metric name used in the wide chip frame.
_METRICS = {
    "ClsPric": "Close",
    "OpnIntrst": "OI",
    "ChngInOpnIntrst": "OI change",
    "TtlTradgVol": "Volume",
}

PARITY_COLUMNS = [
    "Symbol",
    "Expiry",
    "Strike",
    "CE Close",
    "PE Close",
    "CE OI",
    "PE OI",
    "Implied forward",
    "Reference forward",
    "Deviation",
    "Deviation %",
]

SURGE_COLUMNS = [
    "Symbol",
    "Expiry",
    "Strike",
    "Type",
    "Close",
    "OI",
    "OI change",
    "Volume",
    "Buildup",
]

RATIO_COLUMNS = ["Symbol", "Expiry", "CE OI", "PE OI", "Put-call ratio", "CE Volume", "PE Volume"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/zip, application/octet-stream, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=OPTION_COLUMNS)


def _as_frame(raw) -> pd.DataFrame:
    if raw is None:
        return pd.DataFrame()
    return raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)


def _read_zip_csv(payload: bytes) -> pd.DataFrame:
    """Read the bhavcopy CSV out of its zip (or, defensively, raw CSV bytes)."""
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            name = next(
                (n for n in archive.namelist() if n.lower().endswith(".csv")), None
            )
            if name is None:
                return pd.DataFrame()
            with archive.open(name) as handle:
                return pd.read_csv(handle)
    return pd.read_csv(io.BytesIO(payload))


def _parse_futures(frame: pd.DataFrame) -> pd.DataFrame:
    """One ``Future close`` per (Symbol, Expiry) from the bhavcopy's futures rows."""
    required = {"FinInstrmTp", "TckrSymb", "XpryDt", "ClsPric"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=["Symbol", "Expiry", "Future close"])

    futures = frame[frame["FinInstrmTp"].isin(FUTURES_TYPES)].copy()
    if futures.empty:
        return pd.DataFrame(columns=["Symbol", "Expiry", "Future close"])

    futures["Symbol"] = futures["TckrSymb"].astype(str).str.strip().str.upper()
    futures["Expiry"] = pd.to_datetime(futures["XpryDt"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    futures["Future close"] = pd.to_numeric(futures["ClsPric"], errors="coerce")
    futures = futures.dropna(subset=["Symbol", "Expiry", "Future close"])
    if futures.empty:
        return pd.DataFrame(columns=["Symbol", "Expiry", "Future close"])
    return futures.groupby(["Symbol", "Expiry"], as_index=False)[["Future close"]].last()


def parse_fo_bhavcopy(raw) -> pd.DataFrame:
    """Pivot a raw UDiFF F&O bhavcopy into one row per (Symbol, Expiry, Strike).

    ``raw`` is the bhavcopy as a DataFrame (a mapping, a CSV path or a CSV text
    buffer also work). Futures rows and non-call/put rows are dropped. A strike
    that traded only one side keeps the other side as ``NaN`` so parity can skip
    it downstream.
    """
    frame = _as_frame(raw)
    required = {"TckrSymb", "XpryDt", "StrkPric", "OptnTp"}
    if frame.empty or not required.issubset(frame.columns):
        return _empty()

    options = frame[frame["OptnTp"].isin(OPTION_TYPES)].copy()
    if options.empty:
        return _empty()

    options["Date"] = options.get("TradDt")
    options["Symbol"] = options["TckrSymb"].astype(str).str.strip().str.upper()
    options["Expiry"] = pd.to_datetime(options["XpryDt"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    options["Strike"] = pd.to_numeric(options["StrkPric"], errors="coerce")
    options["Underlying price"] = pd.to_numeric(
        options.get("UndrlygPric"), errors="coerce"
    )
    for source, label in _METRICS.items():
        options[label] = pd.to_numeric(options.get(source), errors="coerce")

    options = options.dropna(subset=["Symbol", "Expiry", "Strike"])
    if options.empty:
        return _empty()

    long = options.melt(
        id_vars=["Date", "Symbol", "Expiry", "Strike", "OptnTp", "Underlying price"],
        value_vars=list(_METRICS.values()),
        var_name="Metric",
        value_name="Value",
    )
    wide = long.pivot_table(
        index=["Symbol", "Expiry", "Strike"],
        columns=["OptnTp", "Metric"],
        values="Value",
        aggfunc="last",
    )
    wide.columns = [f"{side} {metric}" for side, metric in wide.columns]
    wide = wide.reset_index()

    underlyings = (
        options.groupby(["Symbol", "Expiry", "Strike"], as_index=False)[
            ["Underlying price"]
        ].last()
    )
    chain = wide.merge(underlyings, on=["Symbol", "Expiry", "Strike"], how="left")

    # The trade date belongs to the file, not the strike; take the last one seen.
    dates = options.groupby(["Symbol", "Expiry", "Strike"], as_index=False)[
        ["Date"]
    ].last()
    chain = chain.merge(dates, on=["Symbol", "Expiry", "Strike"], how="left")

    futures = _parse_futures(frame)
    if futures is not None and not futures.empty:
        chain = chain.merge(futures, on=["Symbol", "Expiry"], how="left")

    for column in OPTION_COLUMNS:
        if column not in chain.columns:
            chain[column] = np.nan
    return chain[OPTION_COLUMNS].sort_values(
        ["Symbol", "Expiry", "Strike"]
    ).reset_index(drop=True)


def implied_forward(chain: pd.DataFrame) -> pd.Series:
    """Per-strike synthetic forward from put-call parity: ``F = K + C - P``."""
    if chain is None or chain.empty:
        return pd.Series(dtype=float)
    return chain["Strike"] + chain["CE Close"] - chain["PE Close"]


def parity_breaks(
    chain: pd.DataFrame,
    min_oi: float = 1000,
    max_moneyness: float = 0.05,
    max_deviation: float = 0.005,
    floor: float = 1.0,
) -> pd.DataFrame:
    """Strikes whose synthetic forward disagrees with its expiry's reference.

    The reference is the expiry's futures close when the bhavcopy carried a
    future, and otherwise the median implied forward across the expiry's liquid
    strikes. A strike is flagged when ``|C - P - (F_ref - K)|`` exceeds the
    larger of ``floor`` (rupees, to sit above quote noise) and ``max_deviation``
    of spot. Only near-the-money strikes (within ``max_moneyness`` of spot) with
    open interest on both legs are considered.
    """
    if chain is None or chain.empty:
        return pd.DataFrame(columns=PARITY_COLUMNS)

    frame = chain.copy()
    for column in ("CE Close", "PE Close", "CE OI", "PE OI", "Underlying price", "Strike"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["Implied forward"] = implied_forward(frame)
    valid = (
        frame["CE Close"].gt(0)
        & frame["PE Close"].gt(0)
        & frame["CE OI"].fillna(0).ge(min_oi)
        & frame["PE OI"].fillna(0).ge(min_oi)
        & frame["Underlying price"].gt(0)
        & frame["Implied forward"].notna()
    )
    frame = frame[valid]
    if frame.empty:
        return pd.DataFrame(columns=PARITY_COLUMNS)

    moneyness = (frame["Strike"] / frame["Underlying price"] - 1).abs()
    frame = frame[moneyness <= max_moneyness]
    if frame.empty:
        return pd.DataFrame(columns=PARITY_COLUMNS)

    median = frame.groupby(["Symbol", "Expiry"])["Implied forward"].transform("median")
    if "Future close" in frame.columns:
        future = pd.to_numeric(frame["Future close"], errors="coerce")
        frame["Reference forward"] = future.fillna(median)
    else:
        frame["Reference forward"] = median
    frame["Deviation"] = frame["Implied forward"] - frame["Reference forward"]
    frame["Deviation %"] = frame["Deviation"] / frame["Underlying price"]

    threshold = np.maximum(floor, max_deviation * frame["Underlying price"])
    frame = frame[frame["Deviation"].abs() > threshold]
    if frame.empty:
        return pd.DataFrame(columns=PARITY_COLUMNS)

    frame = frame.reindex(frame["Deviation"].abs().sort_values(ascending=False).index)
    return frame[PARITY_COLUMNS].reset_index(drop=True)


def oi_surges(
    chain: pd.DataFrame,
    index_only: bool = False,
    top: Optional[int] = 25,
) -> pd.DataFrame:
    """Strikes with the heaviest fresh positioning, by day-over-day OI change.

    ``Buildup`` is the session's OI change over the previous OI — how far the
    open book moved in one day. Contracts that never traded are dropped.
    """
    if chain is None or chain.empty:
        return pd.DataFrame(columns=SURGE_COLUMNS)

    blocks = []
    for side in OPTION_TYPES:
        part = chain[
            [
                "Symbol",
                "Expiry",
                "Strike",
                f"{side} Close",
                f"{side} OI",
                f"{side} OI change",
                f"{side} Volume",
            ]
        ].copy()
        part.columns = ["Symbol", "Expiry", "Strike", "Close", "OI", "OI change", "Volume"]
        part["Type"] = side
        blocks.append(part)

    long = pd.concat(blocks, ignore_index=True)
    for column in ("Close", "OI", "OI change", "Volume"):
        long[column] = pd.to_numeric(long[column], errors="coerce")
    long = long[long["Volume"].fillna(0) > 0]
    if long.empty:
        return pd.DataFrame(columns=SURGE_COLUMNS)

    if index_only:
        long = long[long["Symbol"].isin(INDEX_SYMBOLS)]
        if long.empty:
            return pd.DataFrame(columns=SURGE_COLUMNS)

    previous = long["OI"] - long["OI change"]
    long["Buildup"] = long["OI change"] / previous.where(previous.abs() >= 1)

    long = long.reindex(long["OI change"].abs().sort_values(ascending=False).index)
    if top is not None:
        long = long.head(top)
    return long[SURGE_COLUMNS].reset_index(drop=True)


def put_call_ratio(chain: pd.DataFrame, index_only: bool = False) -> pd.DataFrame:
    """Per (Symbol, Expiry) open interest and put-call ratio."""
    if chain is None or chain.empty:
        return pd.DataFrame(columns=RATIO_COLUMNS)

    frame = chain.copy()
    for column in ("CE OI", "PE OI", "CE Volume", "PE Volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    if index_only:
        frame = frame[frame["Symbol"].isin(INDEX_SYMBOLS)]
        if frame.empty:
            return pd.DataFrame(columns=RATIO_COLUMNS)

    grouped = frame.groupby(["Symbol", "Expiry"], as_index=False)[
        ["CE OI", "PE OI", "CE Volume", "PE Volume"]
    ].sum()
    grouped["Put-call ratio"] = grouped["CE OI"] / grouped["PE OI"].where(
        grouped["PE OI"] > 0
    )
    return grouped[RATIO_COLUMNS]


def _download(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_fo_bhavcopy(trading_day: date, timeout: int = 30) -> pd.DataFrame:
    """Download and parse one trading day's UDiFF F&O bhavcopy (job side)."""
    url = BHAVCOPY_URL.format(day=trading_day.strftime("%Y%m%d"))
    payload = retry_call(lambda: _download(url, timeout))
    return parse_fo_bhavcopy(_read_zip_csv(payload))


def fetch_latest_fo_bhavcopy(
    today: Optional[date] = None, lookback: int = 7, timeout: int = 30
) -> pd.DataFrame:
    """The most recent trading day's bhavcopy, walking back over weekends/holidays."""
    today = today or date.today()
    for offset in range(max(1, lookback)):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:  # NSE does not trade on the weekend
            continue
        try:
            chain = fetch_fo_bhavcopy(day, timeout=timeout)
        except Exception:  # a holiday or a transient outage: try the day before
            continue
        if chain is not None and not chain.empty:
            return chain
    return _empty()


__all__ = [
    "BHAVCOPY_URL",
    "INDEX_SYMBOLS",
    "OPTION_COLUMNS",
    "OPTION_TYPES",
    "PARITY_COLUMNS",
    "RATIO_COLUMNS",
    "SURGE_COLUMNS",
    "fetch_fo_bhavcopy",
    "fetch_latest_fo_bhavcopy",
    "implied_forward",
    "oi_surges",
    "parse_fo_bhavcopy",
    "parity_breaks",
    "put_call_ratio",
]
