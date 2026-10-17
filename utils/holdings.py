"""Canonical holdings — the one shape every broker import lands in.

A broker export is a pile of vendor-specific columns; the analytics pages only
ever need ``Symbol``, ``Total Quantity``, ``Invested Value`` and ``Current
Value``. This module owns the translation:

* :func:`normalize_symbol` — clean a vendor trading symbol down to the NSE code.
* :class:`SymbolMaster` / :func:`resolve` — turn ISIN/trading-symbol/company-name
  into the canonical NSE symbol, preferring the ISIN (the one key that is the
  same at every broker and depository).
* :func:`derive_values` — quantity × price arithmetic, with the cost basis kept
  when no market price is available.
* :func:`merge_positions` — collapse the same ISIN held at two brokers into one
  position (the point of the client book).

Everything here is pure: pandas in, pandas out, no Streamlit and no network, so
the parsers and the resolver are unit-testable on committed fixtures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import pandas as pd

#: The four columns the analytics pages consume — a portfolio is a frame of
#: these and nothing else is required to render the Co-Pilot.
CORE_COLUMNS: Tuple[str, ...] = (
    "Symbol",
    "Total Quantity",
    "Invested Value",
    "Current Value",
)

#: Everything an import may additionally carry. ``Client``/``Broker``/``Account``
#: are what make a book of clients possible later; they are optional today.
CONTEXT_COLUMNS: Tuple[str, ...] = (
    "Client",
    "Broker",
    "Account",
    "ISIN",
    "Company",
    "Sector",
    "Average Price",
    "Current Price",
    "Unrealized P&L",
    "As of",
    "Source",
)

CANONICAL_COLUMNS: Tuple[str, ...] = CORE_COLUMNS + CONTEXT_COLUMNS

#: Exchange series suffixes a trading symbol may carry (``RELIANCE-EQ``).
_SERIES_SUFFIXES = ("-EQ", "-BE", "-BZ", "-BL", "-IL", "-ST", "-SM", "-IS")

#: Words that carry no signal in a company name, dropped before fuzzy matching.
_NAME_STOPWORDS = frozenset(
    {
        "LTD", "LIMITED", "PVT", "PRIVATE", "CO", "COMPANY", "CORP",
        "CORPORATION", "INC", "INDIA", "INDIAN", "THE", "AND", "OF", "&",
    }
)

_ROOT = Path(__file__).resolve().parent.parent
SECTOR_PATH = _ROOT / "data" / "stock-sector.csv"
COMPANIES_PATH = _ROOT / "data" / "all-companies-list.csv"


# --------------------------------------------------------------------------- #
# Symbols
# --------------------------------------------------------------------------- #
def normalize_symbol(value) -> str:
    """Fold a vendor trading symbol into the plain NSE code.

    ``"reliance-eq "`` → ``"RELIANCE"``; ``"NSE:TCS"`` → ``"TCS"``. Genuine
    punctuation inside a symbol (``M&M``, ``BAJAJ-AUTO``) is preserved — only
    known series suffixes and exchange prefixes are stripped.
    """
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "-", "--", "NA", "N/A"}:
        return ""
    for prefix in ("NSE:", "NS:", "NSE-", "BSE:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    if text.endswith(".NS"):
        text = text[:-3]
    for suffix in _SERIES_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return " ".join(text.split())


def is_isin(value) -> bool:
    """True for a 12-character Indian ISIN (``INE002A01018``)."""
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", str(value or "").strip().upper()))


def name_key(value) -> str:
    """A comparable company name: upper-cased, punctuation-free, stopword-free."""
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper())
    tokens = [token for token in text.split() if token not in _NAME_STOPWORDS]
    return " ".join(tokens)


# --------------------------------------------------------------------------- #
# The symbol master
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SymbolMaster:
    """Every way we know how to turn an imported row into an NSE symbol.

    Built from the committed screener exports (``data/stock-sector.csv`` carries
    ISIN ↔ NSE code ↔ sector ↔ company; ``data/all-companies-list.csv`` widens
    the plain-symbol index). A future nightly job can publish a fuller
    ISIN master using the same shape.
    """

    by_isin: Dict[str, str] = field(default_factory=dict)
    by_symbol: Dict[str, str] = field(default_factory=dict)
    by_name: Dict[str, str] = field(default_factory=dict)
    sectors: Dict[str, str] = field(default_factory=dict)
    companies: Dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:  # an empty master is falsy, so callers can check
        return bool(self.by_symbol or self.by_isin)

    @classmethod
    def from_frames(
        cls,
        sectors: Optional[pd.DataFrame] = None,
        companies: Optional[pd.DataFrame] = None,
    ) -> "SymbolMaster":
        master = cls()
        if sectors is not None and not sectors.empty:
            frame = sectors
            isin_col = _pick(frame, ("ISIN",))
            symbol_col = _pick(frame, ("NSE code", "NSE Code", "Symbol"))
            sector_col = _pick(frame, ("Sector",))
            company_col = _pick(frame, ("Company", "Name"))
            positions = list(frame.columns)
            symbol_at = positions.index(symbol_col) if symbol_col else None
            isin_at = positions.index(isin_col) if isin_col else None
            sector_at = positions.index(sector_col) if sector_col else None
            company_at = positions.index(company_col) if company_col else None
            for row in frame.itertuples(index=False, name=None):
                symbol = normalize_symbol(row[symbol_at] if symbol_at is not None else "")
                if not symbol:
                    continue
                master.by_symbol.setdefault(symbol, symbol)
                isin = str(row[isin_at] or "").strip().upper() if isin_at is not None else ""
                if is_isin(isin):
                    master.by_isin.setdefault(isin, symbol)
                sector = str(row[sector_at] or "").strip() if sector_at is not None else ""
                if sector and sector.lower() != "nan":
                    master.sectors.setdefault(symbol, sector)
                company = str(row[company_at] or "").strip() if company_at is not None else ""
                if company and company.lower() != "nan":
                    master.companies.setdefault(symbol, company)
                    key = name_key(company)
                    if key:
                        master.by_name.setdefault(key, symbol)

        if companies is not None and not companies.empty:
            symbol_col = _pick(companies, ("NSE Code", "NSE code", "Symbol"))
            if symbol_col:
                for value in companies[symbol_col].dropna():
                    symbol = normalize_symbol(value)
                    if symbol:
                        master.by_symbol.setdefault(symbol, symbol)
        return master

    @classmethod
    def from_paths(
        cls,
        sector_path: str | Path = SECTOR_PATH,
        companies_path: str | Path = COMPANIES_PATH,
    ) -> "SymbolMaster":
        sectors = _read_csv(sector_path)
        companies = _read_csv(companies_path)
        return cls.from_frames(sectors, companies)

    def sector(self, symbol: str) -> str:
        return self.sectors.get(symbol, "")

    def company(self, symbol: str) -> str:
        return self.companies.get(symbol, "")


def _pick(frame: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    """The first column of ``frame`` whose name matches one of ``names``."""
    lookup = {str(column).strip().lower(): column for column in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def _read_csv(path: str | Path) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
#: ``status`` values, most to least confident. ``unresolved``/``ambiguous`` rows
#: are surfaced for a human to fix rather than silently dropped.
MATCH_STATUSES = ("alias", "isin", "symbol", "name", "ambiguous", "unresolved")


@dataclass(frozen=True)
class Resolution:
    symbol: str
    status: str
    candidates: Tuple[str, ...] = ()


def resolve_one(
    *,
    isin: str = "",
    symbol: str = "",
    name: str = "",
    master: SymbolMaster,
    aliases: Optional[Mapping[str, str]] = None,
) -> Resolution:
    """Resolve a single row, preferring the ISIN, then the symbol, then the name."""
    aliases = aliases or {}
    isin = str(isin or "").strip().upper()
    candidate_symbol = normalize_symbol(symbol)
    alias_map = {str(key).strip().upper(): value for key, value in aliases.items()}

    for key in (isin, candidate_symbol, name_key(name)):
        if key and key in alias_map:
            return Resolution(normalize_symbol(alias_map[key]), "alias")

    if is_isin(isin) and isin in master.by_isin:
        return Resolution(master.by_isin[isin], "isin")

    if candidate_symbol and candidate_symbol in master.by_symbol:
        return Resolution(candidate_symbol, "symbol")

    key = name_key(name)
    if key and key in master.by_name:
        return Resolution(master.by_name[key], "name")

    if key:
        near = sorted(
            {
                resolved
                for candidate, resolved in master.by_name.items()
                if key in candidate or candidate in key
            }
        )
        if len(near) == 1:
            return Resolution(near[0], "name", tuple(near))
        if near:
            return Resolution("", "ambiguous", tuple(near[:8]))

    # Nothing matched. Keep a cleaned symbol if the file gave one, so a brand-new
    # listing still charts; otherwise the row is a human's to fix.
    return Resolution(candidate_symbol, "unresolved")


def resolve(
    frame: pd.DataFrame,
    master: SymbolMaster,
    *,
    aliases: Optional[Mapping[str, str]] = None,
) -> pd.DataFrame:
    """Fill/overwrite ``Symbol`` and add a ``Match`` column across ``frame``.

    The input needs whichever of ``ISIN``, ``Symbol``, ``Company`` it has; the
    output keeps every original column plus the resolved ``Symbol`` and ``Match``.
    """
    out = frame.copy()
    if "Symbol" not in out:
        out["Symbol"] = ""
    for column in ("ISIN", "Company"):
        if column not in out:
            out[column] = ""

    statuses: List[str] = []
    symbols: List[str] = []
    for _, row in out.iterrows():
        resolution = resolve_one(
            isin=row.get("ISIN", ""),
            symbol=row.get("Symbol", ""),
            name=row.get("Company", ""),
            master=master,
            aliases=aliases,
        )
        symbols.append(resolution.symbol)
        statuses.append(resolution.status)
    out["Symbol"] = symbols
    out["Match"] = statuses
    return out


def unresolved(frame: pd.DataFrame) -> pd.DataFrame:
    """The rows a human still has to map (``ambiguous`` or ``unresolved``)."""
    if "Match" not in frame:
        return frame.iloc[0:0]
    return frame[frame["Match"].isin(("ambiguous", "unresolved"))]


def match_summary(frame: pd.DataFrame) -> Dict[str, int]:
    """Counts per match status, in :data:`MATCH_STATUSES` order, zeros included."""
    counts = frame["Match"].value_counts().to_dict() if "Match" in frame else {}
    return {status: int(counts.get(status, 0)) for status in MATCH_STATUSES}


# --------------------------------------------------------------------------- #
# Derived values and the canonical frame
# --------------------------------------------------------------------------- #
def _to_number(value) -> float:
    """Parse a broker number cell: ``₹1,234.50``, ``(120)``, ``—``, ``-``."""
    if value is None or isinstance(value, bool):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("₹", "").replace("%", "")
    if not text or text.lower() in {"nan", "none", "na", "n/a", "-", "--", "—"}:
        return float("nan")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text)
    except ValueError:
        return float("nan")
    return -number if negative else number


def numeric(series: pd.Series) -> pd.Series:
    """Coerce a possibly-formatted column to floats."""
    return series.map(_to_number) if series is not None else pd.Series(dtype=float)


def derive_values(
    frame: pd.DataFrame,
    prices: Optional[Mapping[str, float]] = None,
) -> pd.DataFrame:
    """Quantity × price arithmetic, with a cost-basis fallback.

    ``prices`` maps canonical symbols to a current price — normally the nightly
    snapshot's latest close, so an import is valued consistently regardless of
    the broker's own probably-stale price. A symbol the file prices but the
    lookup does not keeps the file's price.
    """
    out = frame.copy()
    quantity = numeric(out.get("Total Quantity", pd.Series(index=out.index, dtype=float)))
    average = numeric(out.get("Average Price", pd.Series(index=out.index, dtype=float)))
    file_price = numeric(out.get("Current Price", pd.Series(index=out.index, dtype=float)))

    out["Total Quantity"] = quantity
    out["Average Price"] = average
    out["Invested Value"] = quantity * average

    current = file_price.copy()
    current = current.fillna(average)  # no file price? the cost basis is a floor
    if prices:
        looked_up = out["Symbol"].map(lambda symbol: prices.get(symbol, float("nan")))
        looked_up = numeric(looked_up)
        current = looked_up.fillna(current)
    out["Current Price"] = current
    out["Current Value"] = quantity * current
    out["Unrealized P&L"] = out["Current Value"] - out["Invested Value"]
    return out


def to_core(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce a canonical frame to the four columns the analytics pages read."""
    out = frame.copy()
    for column in CORE_COLUMNS:
        if column not in out:
            out[column] = pd.NA
    out = out[out["Symbol"].notna() & (out["Symbol"].astype(str).str.strip() != "")]
    return out[list(CORE_COLUMNS)].reset_index(drop=True)


def merge_positions(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse the same ISIN held across brokers into one position.

    The merge key is the ISIN when the row has a valid one, otherwise the
    symbol; positions are grouped within ``Client`` so a book of clients keeps
    its clients apart. Quantities add, average price is value-weighted, and the
    contributing brokers/sources are recorded rather than lost.
    """
    if frame.empty:
        return frame.copy()

    out = frame.copy()
    for column in ("Client", "Broker", "Source", "As of", "Symbol", "ISIN", "Company", "Sector"):
        if column not in out:
            out[column] = ""
    out["_key"] = [
        isin if is_isin(isin) else f"SYM:{symbol}"
        for isin, symbol in zip(
            out["ISIN"].fillna(""), out["Symbol"].fillna("")
        )
    ]

    grouped = (
        out.groupby(["Client", "_key"], dropna=False)
        .agg(
            Symbol=("Symbol", "first"),
            ISIN=("ISIN", "first"),
            Company=("Company", "first"),
            Sector=("Sector", "first"),
            Total_Quantity=("Total Quantity", "sum"),
            Invested=("Invested Value", "sum"),
            Current_Value=("Current Value", "sum"),
            Brokers=("Broker", lambda values: "+".join(sorted({str(v) for v in values if str(v)}))),
            Sources=("Source", lambda values: "+".join(sorted({str(v) for v in values if str(v)}))),
            As_of=("As of", "max"),
        )
        .reset_index()
        .drop(columns=["_key"])
    )

    grouped = grouped.rename(
        columns={
            "Total_Quantity": "Total Quantity",
            "Invested": "Invested Value",
            "Current_Value": "Current Value",
            "Brokers": "Broker",
            "Sources": "Source",
            "As_of": "As of",
        }
    )
    quantity = grouped["Total Quantity"].where(grouped["Total Quantity"] != 0)
    grouped["Average Price"] = grouped["Invested Value"] / quantity
    grouped["Current Price"] = grouped["Current Value"] / quantity
    grouped["Unrealized P&L"] = grouped["Current Value"] - grouped["Invested Value"]
    return canonical(grouped)


def canonical(frame: pd.DataFrame) -> pd.DataFrame:
    """Put a frame into :data:`CANONICAL_COLUMNS` order, filling what is absent."""
    out = frame.copy()
    for column in CANONICAL_COLUMNS:
        if column not in out:
            out[column] = ""
    return out[list(CANONICAL_COLUMNS)].reset_index(drop=True)


def price_lookup(prices: pd.DataFrame) -> Dict[str, float]:
    """Last non-null price per symbol, from a (dates × symbols) price frame."""
    if prices is None or prices.empty:
        return {}
    latest = prices.sort_index().ffill().iloc[-1]
    return {str(symbol): float(value) for symbol, value in latest.items() if pd.notna(value)}
