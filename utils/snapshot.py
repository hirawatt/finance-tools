"""Nightly market-data snapshots: build once, read from everywhere else.

The Co-Pilot resolves prices, fundamentals, Altman Z inputs, earnings dates and
NSE surveillance lists per request. Fetching those live puts Yahoo and NSE on
the critical path of every cold load, and makes the app's latency a function of
someone else's rate limiter (see the ``perf:`` commit that introduced the
snapshot store).

A scheduled job — :mod:`scripts.build_snapshot` — fetches the curated universe
once a night and writes Parquet blobs plus a manifest to S3-compatible storage.
The app reads the snapshot when it exists, is fresh, and covers the requested
symbols; anything it cannot cover is fetched live and merged in, so an arbitrary
uploaded portfolio still works.

Layering:

* :class:`LocalStore` and :class:`S3Store` move opaque bytes. Streamlit is never
  imported here, so the module is usable from the job and from the app alike.
* The ``*_to_frame`` / ``frame_to_*`` helpers are pure DataFrame conversions.
* :func:`build_universe` and :func:`fetch_universe_data` run in the job.
* :func:`load_prices` and friends are the app-facing read-through helpers.

``prices`` is stored long (``Date``/``Symbol``/``Close``) so coverage can be
checked per symbol; the benchmark rides along under :data:`BENCHMARK_KEY`.
``volumes`` is the same shape with ``Volume``, and ``options`` is the end-of-day
per-strike chain (``utils.options``) the Due Diligence page reads. ``earnings``
deliberately stores the earnings *date* rather than the derived "days away",
which is recomputed on read so a slightly stale snapshot does not report
nonsense.
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from utils.default_risk import fetch_default_risk
from utils.earnings import EARNINGS_COLUMNS, fetch_earnings_calendar
from utils.market_data import (
    BENCHMARK_NAME,
    COMPANY_FIELDS,
    DEFAULT_BENCHMARK,
    fetch_company_data,
    fetch_price_and_volume_history,
    fetch_price_history,
)
from utils.options import OPTION_COLUMNS, fetch_latest_fo_bhavcopy
from utils.surveillance import SURVEILLANCE_COLUMNS, fetch_surveillance
from utils.watchlists import read_watchlists

# Datasets written by the job, one Parquet blob each.
DATASETS = (
    "prices",
    "volumes",
    "company_data",
    "default_risk",
    "earnings",
    "surveillance",
    "options",
)

MANIFEST_NAME = "manifest.json"
PRICE_COLUMNS = ["Date", "Symbol", "Close"]
VOLUME_COLUMNS = ["Date", "Symbol", "Volume"]

# The benchmark is stored as just another symbol, keyed by its Yahoo ticker so it
# cannot collide with an NSE code.
BENCHMARK_KEY = DEFAULT_BENCHMARK

DEFAULT_PERIOD = "5y"
DEFAULT_MAX_AGE = timedelta(hours=36)

# Lookback windows the snapshot can serve by slicing a longer history.
PERIOD_OFFSETS = {
    "6mo": pd.DateOffset(months=6),
    "1y": pd.DateOffset(years=1),
    "2y": pd.DateOffset(years=2),
    "5y": pd.DateOffset(years=5),
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX_DIR = _REPO_ROOT / "indices"
DEFAULT_HOLDINGS = _REPO_ROOT / "data" / "holdings-sample.xlsx"
DEFAULT_LOCAL_DIR = _REPO_ROOT / "snapshots"


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
class LocalStore:
    """A directory on disk. Used for local runs and in tests."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def read(self, name: str) -> Optional[bytes]:
        try:
            return (self.root / name).read_bytes()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            return None

    def write(self, name: str, payload: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a reader never sees a half-written blob.
        temporary = self.root / f".{name}.tmp"
        temporary.write_bytes(payload)
        temporary.replace(self.root / name)


class S3Store:
    """Any S3-compatible bucket: AWS S3, Cloudflare R2, MinIO, Backblaze B2."""

    def __init__(self, bucket: str, prefix: str = "snapshots", client=None, **client_kwargs):
        self.bucket = bucket
        self.prefix = (prefix or "").strip("/")
        if client is not None:
            self._client = client
        else:
            import boto3  # imported lazily so the module works without AWS deps

            self._client = boto3.client("s3", **client_kwargs)

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def read(self, name: str) -> Optional[bytes]:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=self._key(name))
        except Exception:  # a missing/forbidden blob is a cache miss, not an error
            return None
        return obj["Body"].read()

    def write(self, name: str, payload: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=self._key(name), Body=payload)


_ENV_KEYS = {
    "bucket": ("SNAPSHOT_BUCKET",),
    "prefix": ("SNAPSHOT_PREFIX",),
    "local_dir": ("SNAPSHOT_DIR",),
    "endpoint_url": ("SNAPSHOT_ENDPOINT_URL",),
    "region": ("SNAPSHOT_REGION",),
    "access_key": ("SNAPSHOT_ACCESS_KEY", "AWS_ACCESS_KEY_ID"),
    "secret_key": ("SNAPSHOT_SECRET_KEY", "AWS_SECRET_ACCESS_KEY"),
}
_CONFIG_FIELDS = tuple(_ENV_KEYS)


@dataclass(frozen=True)
class SnapshotConfig:
    """Where the snapshot lives.

    Resolved from the environment (the job) or a ``[snapshot]`` secrets table
    (the app), with the environment as the fallback for anything unset. Without
    a bucket this degrades to a local directory, which keeps local development
    working with no configuration at all.
    """

    bucket: Optional[str] = None
    prefix: str = "snapshots"
    local_dir: Optional[Path] = None
    endpoint_url: Optional[str] = None
    region: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = None) -> "SnapshotConfig":
        return cls.from_mapping({}, environ)

    @classmethod
    def from_secrets(cls, secrets: Optional[Mapping[str, Any]]) -> "SnapshotConfig":
        """Build from a full secrets mapping containing a ``[snapshot]`` table."""
        table = dict((secrets or {}).get("snapshot") or {})
        return cls.from_mapping(table)

    @classmethod
    def from_mapping(
        cls,
        table: Optional[Mapping[str, Any]] = None,
        environ: Optional[Mapping[str, str]] = None,
    ) -> "SnapshotConfig":
        environ = os.environ if environ is None else environ
        values: Dict[str, Any] = {"prefix": "snapshots"}

        for key, names in _ENV_KEYS.items():
            for name in names:
                if environ.get(name):
                    values[key] = environ[name]
                    break

        for key in _CONFIG_FIELDS:
            value = (table or {}).get(key)
            if value not in (None, ""):
                values[key] = value

        if values.get("local_dir"):
            values["local_dir"] = Path(values["local_dir"]).expanduser()
        return cls(**{k: v for k, v in values.items() if k in _CONFIG_FIELDS})

    @property
    def uses_object_storage(self) -> bool:
        return bool(self.bucket)

    def store(self) -> "LocalStore | S3Store":
        if not self.bucket:
            return LocalStore(self.local_dir or DEFAULT_LOCAL_DIR)

        kwargs: Dict[str, Any] = {}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.region:
            kwargs["region_name"] = self.region
        if self.access_key:
            kwargs["aws_access_key_id"] = self.access_key
        if self.secret_key:
            kwargs["aws_secret_access_key"] = self.secret_key
        return S3Store(self.bucket, self.prefix, **kwargs)


# --------------------------------------------------------------------------- #
# Manifest and freshness
# --------------------------------------------------------------------------- #
def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_fresh(
    manifest: Optional[Mapping[str, Any]],
    max_age: timedelta = DEFAULT_MAX_AGE,
    now: Optional[datetime] = None,
) -> bool:
    """Whether a manifest was generated within ``max_age`` of ``now``."""
    if not manifest:
        return False
    generated = _parse_timestamp(manifest.get("generated_at"))
    if generated is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now - generated
    # Tolerate a little clock skew between the job and the reader.
    return -timedelta(hours=1) <= age <= max_age


@dataclass(frozen=True)
class Snapshot:
    """A fresh snapshot: its manifest plus whatever datasets could be read."""

    manifest: Dict[str, Any] = field(default_factory=dict)
    frames: Dict[str, pd.DataFrame] = field(default_factory=dict)


def read_snapshot(
    store: Optional[object],
    max_age: timedelta = DEFAULT_MAX_AGE,
    now: Optional[datetime] = None,
) -> Optional[Snapshot]:
    """Read a fresh snapshot, or ``None`` when there is nothing usable."""
    if store is None:
        return None

    raw = store.read(MANIFEST_NAME)  # type: ignore[attr-defined]
    if raw is None:
        return None
    try:
        manifest = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not is_fresh(manifest, max_age=max_age, now=now):
        return None

    frames: Dict[str, pd.DataFrame] = {}
    for name in DATASETS:
        payload = store.read(f"{name}.parquet")  # type: ignore[attr-defined]
        if payload is None:
            continue
        try:
            frames[name] = pd.read_parquet(io.BytesIO(payload))
        except Exception:  # a corrupt blob must not break the page
            continue

    return Snapshot(manifest=manifest, frames=frames)


# --------------------------------------------------------------------------- #
# Frame conversions (pure)
# --------------------------------------------------------------------------- #
def prices_to_frame(
    prices: Optional[pd.DataFrame], benchmark: Optional[pd.Series]
) -> pd.DataFrame:
    """Long ``Date``/``Symbol``/``Close`` frame, benchmark included under its ticker."""
    blocks: List[pd.DataFrame] = []

    if prices is not None and not prices.empty:
        long = (
            prices.reset_index(names="Date")
            .melt(id_vars="Date", var_name="Symbol", value_name="Close")
            .dropna(subset=["Close"])
        )
        blocks.append(long[PRICE_COLUMNS])

    if benchmark is not None and not benchmark.empty:
        blocks.append(
            pd.DataFrame(
                {
                    "Date": benchmark.index,
                    "Symbol": BENCHMARK_KEY,
                    "Close": benchmark.to_numpy(),
                }
            )
        )

    if not blocks:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    return pd.concat(blocks, ignore_index=True)


def frame_to_prices(
    frame: Optional[pd.DataFrame],
) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Rebuild the wide close frame and the benchmark series from stored prices."""
    if frame is None or frame.empty or not set(PRICE_COLUMNS).issubset(frame.columns):
        return pd.DataFrame(), None

    wide = frame.pivot(index="Date", columns="Symbol", values="Close").sort_index()
    wide.columns.name = None

    benchmark = None
    if BENCHMARK_KEY in wide.columns:
        benchmark = wide[BENCHMARK_KEY].dropna().rename(BENCHMARK_NAME)
        wide = wide.drop(columns=[BENCHMARK_KEY])
    return wide, benchmark


def volumes_to_frame(volumes: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Long ``Date``/``Symbol``/``Volume`` frame from a wide volume frame."""
    if volumes is None or volumes.empty:
        return pd.DataFrame(columns=VOLUME_COLUMNS)
    long = (
        volumes.reset_index(names="Date")
        .melt(id_vars="Date", var_name="Symbol", value_name="Volume")
        .dropna(subset=["Volume"])
    )
    return long[VOLUME_COLUMNS]


def frame_to_volumes(frame: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Rebuild the wide volume frame (index ``Date``, one column per symbol)."""
    if frame is None or frame.empty or not set(VOLUME_COLUMNS).issubset(frame.columns):
        return pd.DataFrame()

    wide = frame.pivot(index="Date", columns="Symbol", values="Volume").sort_index()
    wide.columns.name = None
    return wide


def earnings_to_frame(frame: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Store the earnings *date* as text; "days away" is derived on read."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Symbol", "Date", "EPS estimate", "Revenue estimate"])

    out = frame.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    return out[["Symbol", "Date", "EPS estimate", "Revenue estimate"]]


def frame_to_earnings(
    frame: Optional[pd.DataFrame], today: Optional[date] = None
) -> pd.DataFrame:
    """Rebuild an earnings frame, recomputing "days away" and dropping past dates."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=EARNINGS_COLUMNS)

    out = frame.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.date
    current = today or date.today()
    out["Days away"] = [(value - current).days for value in out["Date"]]
    out = out[out["Days away"] >= 0]
    return out[EARNINGS_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Universe (job side)
# --------------------------------------------------------------------------- #
def _clean_symbols(symbols: Iterable[str]) -> List[str]:
    return [s for s in dict.fromkeys(str(symbol).strip() for symbol in symbols) if s]


def symbols_from_index_dir(directory: Path | str) -> List[str]:
    """Every symbol in the curated watchlists under ``indices/``.

    Reads all rows of each watchlist (long lists wrap), and expands a token
    that names another watchlist instead of treating it as a ticker.
    """
    return [
        symbol
        for symbols in read_watchlists(directory).values()
        for symbol in symbols
    ]


def symbols_from_holdings(path: Path | str) -> List[str]:
    """Symbols in a holdings export, in file order and uppercased.

    Routed through the broker importer so the nightly universe job understands
    any supported broker file, not just the Zerodha layout it was written for.
    """
    from utils.brokers import import_holdings
    from utils.holdings import SymbolMaster

    path = Path(path)
    try:
        result = import_holdings(path.read_bytes(), path.name, master=SymbolMaster())
    except Exception:  # an unreadable or unmapped file contributes no symbols
        return []

    symbols: List[str] = []
    for value in result.holdings.get("Symbol", []):
        symbol = str(value).strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def build_universe(
    index_dir: Path | str = DEFAULT_INDEX_DIR,
    holdings_path: Path | str = DEFAULT_HOLDINGS,
) -> List[str]:
    """The symbol universe the nightly job snapshots.

    Every curated watchlist in ``indices/`` plus the sample portfolio. The
    screener exports (``stock-sector.csv``, ``all-companies-list.csv``) are
    deliberately excluded: at ~2,200 symbols they would mean ~9,000 upstream
    requests a night.
    """
    symbols = symbols_from_index_dir(index_dir) + symbols_from_holdings(holdings_path)
    return sorted(dict.fromkeys(symbols))


# --------------------------------------------------------------------------- #
# Build (job side)
# --------------------------------------------------------------------------- #
def fetch_universe_data(
    symbols: Sequence[str],
    period: str = DEFAULT_PERIOD,
    benchmark: str = DEFAULT_BENCHMARK,
    today: Optional[date] = None,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, List[str]]]:
    """Fetch every dataset for ``symbols`` as flat, Parquet-ready frames.

    Returns ``(frames, failures)``. A dataset that raises is omitted from
    ``frames`` and recorded in ``failures``, so one flaky provider does not
    cost the whole night's snapshot. The same map also names the symbols Yahoo
    returned no prices for, so an incomplete universe is visible in the
    manifest instead of only in the provider's log.
    """
    frames: Dict[str, pd.DataFrame] = {}
    failures: Dict[str, List[str]] = {}

    def capture(name: str, build: Callable[[], pd.DataFrame]) -> None:
        """Record one dataset, so one flaky provider cannot cost the night."""
        try:
            frames[name] = build()
        except Exception as exc:
            failures[name] = [f"{type(exc).__name__}: {exc}"]

    company = pd.DataFrame()

    def company_data() -> pd.DataFrame:
        # Kept in the enclosing scope: the Z-scores below need the market caps.
        nonlocal company
        company = fetch_company_data(symbols, COMPANY_FIELDS)
        return company.reset_index()

    def default_risk() -> pd.DataFrame:
        caps: Dict[str, float] = {}
        if not company.empty and "Market cap" in company.columns:
            caps = company["Market cap"].dropna().to_dict()
        return fetch_default_risk(symbols, pd.Series(caps, dtype=float)).reset_index()

    def price_and_volume() -> None:
        """One Yahoo pass fills both the price and the volume datasets."""
        clean = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]
        prices, benchmark_series, volumes = fetch_price_and_volume_history(
            clean, period=period, benchmark=benchmark
        )
        frames["prices"] = prices_to_frame(prices, benchmark_series)
        frames["volumes"] = volumes_to_frame(volumes)
        # `_tidy` drops tickers Yahoo has no data for, so the manifest would
        # otherwise claim the full universe with nothing recording the gap.
        uncovered = [symbol for symbol in dict.fromkeys(clean) if symbol not in prices.columns]
        if uncovered:
            failures["prices"] = [f"no data from Yahoo: {', '.join(uncovered)}"]

    try:
        price_and_volume()
    except Exception as exc:  # one provider outage must not cost the night
        failures["prices"] = [f"{type(exc).__name__}: {exc}"]

    capture("company_data", company_data)
    capture("default_risk", default_risk)
    capture(
        "earnings",
        lambda: earnings_to_frame(fetch_earnings_calendar(symbols, today=today)),
    )
    capture("surveillance", fetch_surveillance)
    capture("options", lambda: fetch_latest_fo_bhavcopy(today=today))

    return frames, failures


def write_snapshot(
    store: object,
    frames: Mapping[str, pd.DataFrame],
    generated_at: Optional[datetime] = None,
    period: str = DEFAULT_PERIOD,
    benchmark: str = DEFAULT_BENCHMARK,
    universe: Sequence[str] = (),
    failures: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    """Write the blobs, then the manifest. Returns the manifest.

    The manifest goes last so a reader cannot observe a manifest whose blobs are
    still being uploaded.
    """
    stamp = generated_at or datetime.now(timezone.utc)
    manifest: Dict[str, Any] = {
        "generated_at": stamp.astimezone(timezone.utc).isoformat(),
        "period": period,
        "benchmark": benchmark,
        "universe_size": len(list(universe)),
        "datasets": {name: {"rows": int(len(frame))} for name, frame in frames.items()},
        "failures": {name: list(errors) for name, errors in (failures or {}).items()},
    }

    for name, frame in frames.items():
        store.write(f"{name}.parquet", frame.to_parquet(index=False))  # type: ignore[attr-defined]
    store.write(MANIFEST_NAME, json.dumps(manifest, indent=2).encode("utf-8"))  # type: ignore[attr-defined]
    return manifest


# --------------------------------------------------------------------------- #
# Read-through helpers (app side)
# --------------------------------------------------------------------------- #
def _resolve(
    requested: Sequence[str], available: Iterable[str]
) -> Tuple[Dict[str, str], List[str]]:
    """Match requested symbols to stored ones case-insensitively.

    Returns ``({requested: stored_name}, [uncovered_requested])`` in request order.
    """
    lookup = {str(name).strip().upper(): str(name) for name in available}
    mapping: Dict[str, str] = {}
    missing: List[str] = []
    for symbol in requested:
        match = lookup.get(str(symbol).strip().upper())
        if match is None:
            missing.append(symbol)
        else:
            mapping[symbol] = match
    return mapping, missing


def _slice_period(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    offset = PERIOD_OFFSETS.get(period)
    if offset is None or frame.empty:
        return frame
    return frame.loc[frame.index >= frame.index.max() - offset]


def _fresh_snapshot(
    store: Optional[object],
    now: Optional[datetime] = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> Optional[Snapshot]:
    """Read a snapshot, treating any failure as "no snapshot"."""
    if store is None:
        return None
    try:
        return read_snapshot(store, max_age=max_age, now=now)
    except Exception:
        return None


def load_prices(
    symbols: Iterable[str],
    period: str = "1y",
    benchmark: Optional[str] = DEFAULT_BENCHMARK,
    store: Optional[object] = None,
    now: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Snapshot-first price history, falling back to a live fetch."""
    requested = _clean_symbols(symbols)

    # A different benchmark than the one we snapshot cannot be served from it.
    if store is None or benchmark not in (None, BENCHMARK_KEY) or period not in PERIOD_OFFSETS:
        return fetch_price_history(requested, period=period, benchmark=benchmark)

    snapshot = _fresh_snapshot(store, now)
    prices = pd.DataFrame()
    benchmark_series = None
    if snapshot is not None:
        prices, benchmark_series = frame_to_prices(snapshot.frames.get("prices"))

    if prices.empty:
        return fetch_price_history(requested, period=period, benchmark=benchmark)

    mapping, missing = _resolve(requested, prices.columns)
    if mapping:
        covered = _slice_period(prices[[mapping[s] for s in mapping]], period).copy()
        covered.columns = list(mapping)
    else:
        covered = prices.iloc[0:0]

    if not missing:
        return covered.sort_index(), benchmark_series

    live, _ = fetch_price_history(missing, period=period, benchmark=None)
    if live is None or live.empty:
        return covered.sort_index(), benchmark_series
    if covered.shape[1] == 0:
        return live.sort_index(), benchmark_series
    return covered.join(live, how="outer").sort_index(), benchmark_series


def load_company_data(
    symbols: Iterable[str],
    fields: Mapping[str, str] = COMPANY_FIELDS,
    store: Optional[object] = None,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Snapshot-first fundamentals, falling back to a live fetch."""
    requested = _clean_symbols(symbols)
    labels = list(dict.fromkeys(fields.values()))

    snapshot = _fresh_snapshot(store, now)
    stored = None
    if snapshot is not None:
        frame = snapshot.frames.get("company_data")
        if frame is not None and "Symbol" in frame.columns and set(labels).issubset(frame.columns):
            stored = frame.set_index("Symbol")

    if stored is None or stored.empty:
        return fetch_company_data(requested, fields)

    mapping, missing = _resolve(requested, stored.index)
    covered = _take_rows(stored, mapping, labels)
    if not missing:
        return covered

    live = fetch_company_data(missing, fields)
    if covered.empty:
        return live
    return pd.concat([covered, live])


def load_default_risk(
    symbols: Iterable[str],
    market_caps: Optional[pd.Series] = None,
    store: Optional[object] = None,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Snapshot-first Altman Z-scores, falling back to a live fetch."""
    requested = _clean_symbols(symbols)
    caps = market_caps if market_caps is not None else pd.Series(dtype=float)

    snapshot = _fresh_snapshot(store, now)
    stored = None
    if snapshot is not None:
        frame = snapshot.frames.get("default_risk")
        if frame is not None and "Symbol" in frame.columns:
            stored = frame.set_index("Symbol")

    if stored is None or stored.empty:
        return fetch_default_risk(requested, caps)

    mapping, missing = _resolve(requested, stored.index)
    covered = _take_rows(stored, mapping)
    if not missing:
        return covered

    live = fetch_default_risk(missing, caps)
    if covered.empty:
        return live
    return pd.concat([covered, live])


def load_earnings(
    symbols: Iterable[str],
    store: Optional[object] = None,
    now: Optional[datetime] = None,
    today: Optional[date] = None,
) -> pd.DataFrame:
    """Snapshot-first earnings calendar, falling back to a live fetch."""
    requested = _clean_symbols(symbols)

    snapshot = _fresh_snapshot(store, now)
    stored = None
    if snapshot is not None:
        frame = snapshot.frames.get("earnings")
        if frame is not None and "Symbol" in frame.columns:
            stored = frame_to_earnings(frame, today=today)

    if stored is None or stored.empty:
        return fetch_earnings_calendar(requested, today=today)

    mapping, missing = _resolve(requested, stored["Symbol"])
    covered = stored[stored["Symbol"].isin(mapping.values())].copy()
    if mapping:
        covered["Symbol"] = covered["Symbol"].map({v: k for k, v in mapping.items()})

    if not missing:
        return covered.sort_values("Date").reset_index(drop=True)

    live = fetch_earnings_calendar(missing, today=today)
    if covered.empty:
        return live
    return pd.concat([covered, live]).sort_values("Date").reset_index(drop=True)


def load_surveillance(
    store: Optional[object] = None,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Snapshot-first NSE surveillance lists, falling back to a live fetch."""
    snapshot = _fresh_snapshot(store, now)
    if snapshot is not None:
        frame = snapshot.frames.get("surveillance")
        if frame is not None and not frame.empty:
            if set(SURVEILLANCE_COLUMNS).issubset(frame.columns):
                return frame[SURVEILLANCE_COLUMNS].reset_index(drop=True)
            return frame

    return fetch_surveillance()


def load_snapshot_prices(
    symbols: Iterable[str],
    period: str = "1y",
    store: Optional[object] = None,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Snapshot-only closes, or an empty frame. Never falls back to a fetch.

    The Due Diligence page is deliberately snapshot-only, so it can guarantee it
    never touches a live provider; :func:`load_prices` keeps the live fallback
    the Co-Pilot relies on.
    """
    requested = _clean_symbols(symbols)
    snapshot = _fresh_snapshot(store, now)
    if snapshot is None:
        return pd.DataFrame()
    prices, _ = frame_to_prices(snapshot.frames.get("prices"))
    return _slice_symbols(prices, requested, period)


def load_volumes(
    symbols: Iterable[str],
    period: str = "1y",
    store: Optional[object] = None,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Snapshot-only traded volume, or an empty frame. Never fetches."""
    requested = _clean_symbols(symbols)
    snapshot = _fresh_snapshot(store, now)
    if snapshot is None:
        return pd.DataFrame()
    volumes = frame_to_volumes(snapshot.frames.get("volumes"))
    return _slice_symbols(volumes, requested, period)


def load_options(
    store: Optional[object] = None,
    now: Optional[datetime] = None,
    symbols: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Snapshot-only end-of-day option chain, or an empty frame. Never fetches."""
    snapshot = _fresh_snapshot(store, now)
    if snapshot is None:
        return pd.DataFrame(columns=OPTION_COLUMNS)
    frame = snapshot.frames.get("options")
    if frame is None or frame.empty:
        return pd.DataFrame(columns=OPTION_COLUMNS)

    frame = frame.reset_index(drop=True)
    if symbols is not None:
        wanted = {str(symbol).strip().upper() for symbol in symbols}
        frame = frame[frame["Symbol"].isin(wanted)].reset_index(drop=True)
    return frame


def _slice_symbols(
    wide: pd.DataFrame, requested: Sequence[str], period: str
) -> pd.DataFrame:
    """Resolve requested symbols against a snapshot frame and slice the period."""
    if wide is None or wide.empty:
        return pd.DataFrame()
    mapping, _ = _resolve(requested, wide.columns)
    if not mapping:
        return pd.DataFrame()
    covered = _slice_period(wide[[mapping[symbol] for symbol in mapping]], period).copy()
    covered.columns = list(mapping)
    return covered.sort_index()


def _take_rows(
    stored: pd.DataFrame, mapping: Mapping[str, str], columns: Optional[Sequence[str]] = None
) -> pd.DataFrame:
    """Rows of ``stored`` for ``mapping``, reindexed to the requested spellings."""
    selected = list(columns) if columns is not None else list(stored.columns)
    if not mapping:
        return stored.iloc[0:0][selected]
    covered = stored.loc[[mapping[symbol] for symbol in mapping], selected].copy()
    covered.index = pd.Index(list(mapping), name="Symbol")
    return covered


__all__ = [
    "DATASETS",
    "DEFAULT_MAX_AGE",
    "DEFAULT_PERIOD",
    "LocalStore",
    "S3Store",
    "Snapshot",
    "SnapshotConfig",
    "VOLUME_COLUMNS",
    "build_universe",
    "earnings_to_frame",
    "fetch_universe_data",
    "frame_to_earnings",
    "frame_to_prices",
    "frame_to_volumes",
    "is_fresh",
    "load_company_data",
    "load_default_risk",
    "load_earnings",
    "load_options",
    "load_prices",
    "load_snapshot_prices",
    "load_surveillance",
    "load_volumes",
    "prices_to_frame",
    "read_snapshot",
    "symbols_from_holdings",
    "symbols_from_index_dir",
    "volumes_to_frame",
    "write_snapshot",
]
