"""Reading broker holdings exports into a common table.

Every broker ships holdings as a spreadsheet or CSV with its own column names and
its own preamble (client id, statement date, logo rows) before the real header.
A :class:`BrokerProfile` captures just enough to handle one broker: the header
*tokens* that identify its file, the column aliases that map into our target
columns, and — for Zerodha — the several quantity columns that have to be summed.

Detection is deliberately content-based (the header text, not the filename),
because exports drift and clients rename files. When nothing matches, the generic
profile plus a saved column mapping still imports the file.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple

import pandas as pd

#: The columns a profile maps into. ``holdings`` fills in what is absent.
TARGET_COLUMNS: Tuple[str, ...] = (
    "Symbol",
    "ISIN",
    "Company",
    "Sector",
    "Total Quantity",
    "Average Price",
    "Current Price",
    "Unrealized P&L",
    "Client",
    "Account",
)

#: Aliases every profile starts from, so a broker's one extra spelling does not
#: need its own entry. The first alias present in the sheet wins.
COMMON_ALIASES: Mapping[str, Tuple[str, ...]] = {
    "Symbol": (
        "Symbol", "NSE Symbol", "Trading Symbol", "NSE code", "NSE Code",
        "Instrument", "Scrip", "Scrip Code", "Stock Symbol", "Ticker",
    ),
    "ISIN": ("ISIN", "ISIN Code", "ISIN No", "ISIN No."),
    "Company": ("Company", "Company Name", "Stock Name", "Security Name", "Name", "Scrip Name"),
    "Sector": ("Sector", "Industry", "Sector Name"),
    "Average Price": (
        "Average Price", "Avg Price", "Avg. Price", "Avg. Cost Price",
        "Average Cost Price", "Average buy price", "Avg Buy Price", "Buy Price",
        "Avg. cost price", "Average Cost", "Cost Price",
    ),
    "Current Price": (
        "Current Price", "Previous Closing Price", "Closing Price", "LTP",
        "Market Price", "Current Market Price", "Last Price", "CMP",
    ),
    "Total Quantity": ("Quantity", "Qty", "Total Quantity", "Net Quantity", "Units", "Holding Quantity"),
    "Unrealized P&L": ("Unrealized P&L", "Unrealised P&L", "P&L", "PnL", "Gain/Loss"),
}


@dataclass(frozen=True)
class BrokerProfile:
    """How to read one broker's holdings export."""

    name: str
    #: Header tokens that must all appear in the same row for a confident match.
    signature: Tuple[str, ...]
    #: Column aliases for this broker, merged over :data:`COMMON_ALIASES`.
    columns: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    #: Columns to sum into ``Total Quantity`` (Zerodha's five quantity buckets).
    quantity_sources: Tuple[str, ...] = ()
    #: The token a plain header hunt looks for when the signature is absent.
    header_token: str = "symbol"
    #: Copy for the import page's "how to export" expander.
    export_url: str = ""
    export_steps: str = ""
    notes: str = ""

    def aliases(self, target: str) -> Tuple[str, ...]:
        own = self.columns.get(target, ())
        return tuple(own) + tuple(COMMON_ALIASES.get(target, ()))


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def read_raw(data: bytes, filename: str = "") -> pd.DataFrame:
    """Read any supported upload into a header-less frame of raw cells.

    Keeping the frame header-less is what lets us find the real header wherever
    the broker put it, instead of hard-coding a row number.
    """
    suffix = Path(filename or "").suffix.lower()
    buffer = io.BytesIO(data)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(buffer, header=None, sheet_name=0)

    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            buffer.seek(0)
            return pd.read_csv(
                buffer,
                header=None,
                dtype=str,
                skip_blank_lines=False,
                engine="python",
                encoding=encoding,
            )
        except (UnicodeDecodeError, UnicodeError) as error:  # try the next encoding
            last_error = error
    raise ValueError(f"Could not read the file: {last_error}")


def _row_text(raw: pd.DataFrame, index: int) -> str:
    return " ".join(str(cell).lower() for cell in raw.iloc[index] if pd.notna(cell))


def find_signature_row(
    raw: pd.DataFrame, tokens: Sequence[str], limit: int = 80
) -> Optional[int]:
    """The first row containing every one of ``tokens`` (case-insensitive)."""
    if not tokens:
        return None
    wanted = tuple(token.lower() for token in tokens)
    for index in range(min(limit, len(raw))):
        text = _row_text(raw, index)
        if all(token in text for token in wanted):
            return index
    return None


def find_header_row(raw: pd.DataFrame, token: str = "symbol", limit: int = 80) -> Optional[int]:
    """The first row whose cells contain ``token`` — the fallback header hunt."""
    return find_signature_row(raw, (token,), limit=limit)


def find_alias_row(
    raw: pd.DataFrame, profile: "BrokerProfile", limit: int = 80
) -> Optional[int]:
    """The first row containing any of the profile's *explicit* column names.

    Used when a saved mapping's own source headers are the only clue to where
    the table starts — e.g. a sheet whose symbol column is headed ``Scrip``.
    """
    tokens = {alias.lower() for aliases in profile.columns.values() for alias in aliases}
    if not tokens:
        return None
    for index in range(min(limit, len(raw))):
        text = _row_text(raw, index)
        if any(token in text for token in tokens):
            return index
    return None


def slice_table(raw: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Turn a header-less frame into a table starting at ``header_row``."""
    header = [str(cell).strip() for cell in raw.iloc[header_row]]
    body = raw.iloc[header_row + 1 :].reset_index(drop=True).copy()
    body.columns = header
    # Drop unnamed leading index columns and any footer that is entirely blank.
    keep = [
        column
        for column in body.columns
        if column and column.lower() not in {"nan", "unnamed: 0", "unnamed: 1"}
    ]
    body = body.loc[:, keep]
    body = body.dropna(how="all")
    return body.reset_index(drop=True)


def map_columns(table: pd.DataFrame, profile: BrokerProfile) -> pd.DataFrame:
    """Apply a profile's aliases, producing the :data:`TARGET_COLUMNS` subset."""
    lookup = {str(column).strip().lower(): column for column in table.columns}
    mapped = pd.DataFrame(index=table.index)
    for target in TARGET_COLUMNS:
        for alias in profile.aliases(target):
            source = lookup.get(alias.strip().lower())
            if source is not None:
                mapped[target] = table[source]
                break
    return mapped


def guess_mapping(
    table: pd.DataFrame, profile: Optional[BrokerProfile] = None
) -> Dict[str, str]:
    """Best-guess ``target → source column`` for a mapping editor's defaults."""
    if profile is None:
        profile = BrokerProfile(name="Generic", signature=())
    lookup = {str(column).strip().lower(): str(column) for column in table.columns}
    guessed: Dict[str, str] = {}
    for target in TARGET_COLUMNS:
        for alias in profile.aliases(target):
            source = lookup.get(alias.strip().lower())
            if source is not None:
                guessed[target] = source
                break
    return guessed


def _quantity(mapped: pd.DataFrame, table: pd.DataFrame, profile: BrokerProfile) -> pd.Series:
    """Total quantity: the profile's summed buckets, else the plain column."""
    if profile.quantity_sources:
        lookup = {str(column).strip().lower(): column for column in table.columns}
        present = [lookup[source.strip().lower()] for source in profile.quantity_sources if source.strip().lower() in lookup]
        if present:
            from utils.holdings import numeric

            return sum((numeric(table[column]) for column in present), start=pd.Series(0.0, index=table.index))
    if "Total Quantity" in mapped:
        return mapped["Total Quantity"]
    return pd.Series(pd.NA, index=table.index)


def parse(data: bytes, filename: str, profile: BrokerProfile) -> pd.DataFrame:
    """Read ``data`` with ``profile``, returning the mapped target table."""
    raw = read_raw(data, filename)
    header_row = find_signature_row(raw, profile.signature)
    if header_row is None:
        header_row = find_alias_row(raw, profile)
    if header_row is None:
        header_row = find_header_row(raw, profile.header_token)
    if header_row is None:
        raise ValueError("No holdings table found in the file.")

    table = slice_table(raw, header_row)
    mapped = map_columns(table, profile)
    mapped["Total Quantity"] = _quantity(mapped, table, profile)
    mapped["Source"] = filename
    return mapped.reset_index(drop=True)
