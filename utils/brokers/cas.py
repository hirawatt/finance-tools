"""Consolidated Account Statement (CDSL/NSDL CAS) PDF import.

A CAS is the one statement that covers every demat account and broker a person
holds, which is why it is the strategic import path: one file instead of an
export per broker.

These PDFs are tables, so the extractor reads tables first and only falls back to
a line scan when a page has none. Two honest limits, both surfaced to the user:
layouts vary between the depositories (and between CAS versions), so the rows it
cannot read are reported rather than dropped; and a CAS carries **no purchase
price**, so imported holdings have no cost basis — the value is right and the P&L
reads as flat.
"""

from __future__ import annotations

import io
import re
from typing import Dict, List, Optional

import pandas as pd

from utils.holdings import to_number

#: An Indian ISIN, the key we resolve the symbol from.
ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

#: What the extractor produces — the importer resolves and values it like any
#: other mapped frame.
EXTRACTED_COLUMNS = ("ISIN", "Company", "Total Quantity", "Current Price")

_NAME_TOKENS = ("security", "scrip", "company", "name", "description")
_QUANTITY_TOKENS = ("quant", "qty", "units", "balance")
_VALUE_TOKENS = ("value", "amount")
_PRICE_TOKENS = ("price", "rate", "nav")


def _column(header, tokens, *, exclude=()) -> Optional[int]:
    """The first column whose heading carries one of ``tokens``."""
    for index, cell in enumerate(header):
        text = str(cell or "").strip().lower()
        if any(token in text for token in tokens) and not any(bad in text for bad in exclude):
            return index
    return None


def _cell(row, index):
    if index is None or index >= len(row):
        return ""
    return row[index]


def _from_table(table) -> List[Dict[str, object]]:
    """Rows of a holdings table — the reliable path for a real CAS."""
    if not table or len(table) < 2:
        return []
    header = table[0]
    isin_at = _column(header, ("isin",))
    if isin_at is None:
        return []

    name_at = _column(header, _NAME_TOKENS)
    quantity_at = _column(header, _QUANTITY_TOKENS)
    price_at = _column(header, _PRICE_TOKENS)
    value_at = _column(header, _VALUE_TOKENS, exclude=("total", "grand"))

    rows: List[Dict[str, object]] = []
    for raw in table[1:]:
        isin = str(_cell(raw, isin_at) or "").strip().upper()
        if not ISIN_RE.fullmatch(isin):
            continue
        quantity = to_number(_cell(raw, quantity_at)) if quantity_at is not None else float("nan")
        price = to_number(_cell(raw, price_at)) if price_at is not None else float("nan")
        value = to_number(_cell(raw, value_at)) if value_at is not None else float("nan")
        if pd.isna(price) and not pd.isna(value) and quantity:
            price = value / quantity
        rows.append(
            {
                "ISIN": isin,
                "Company": str(_cell(raw, name_at) or "").strip(),
                "Total Quantity": quantity,
                "Current Price": price,
            }
        )
    return rows


def _from_text(text: str) -> List[Dict[str, object]]:
    """A conservative line scan, for a page whose table we could not read.

    Only the ISIN and a quantity are taken; a CAS line rarely carries a value we
    can trust positionally, and the resolver supplies the company from the ISIN.
    """
    rows: List[Dict[str, object]] = []
    for line in text.splitlines():
        match = ISIN_RE.search(line)
        if match is None:
            continue
        name = line[: match.start()].strip(" |\t")
        numbers = NUMBER_RE.findall(line[match.end() :])
        quantity = float("nan")
        for token in numbers:
            candidate = to_number(token)
            if not pd.isna(candidate) and float(candidate).is_integer():
                quantity = candidate
                break
        rows.append(
            {
                "ISIN": match.group(1),
                "Company": name,
                "Total Quantity": quantity,
                "Current Price": float("nan"),
            }
        )
    return rows


def _explain(error: Exception) -> str:
    # pdfminer wraps PDFPasswordIncorrect in a PdfminerException whose message is
    # empty, so the type name and the args are the reliable signals, not the text.
    signature = f"{type(error).__name__} {error} {error.args!r}".lower()
    if "password" in signature:
        return (
            "The statement is password-protected. Enter the password the "
            "depository uses — usually your PAN plus date of birth."
        )
    return f"Could not read the statement: {error}"


def extract(data: bytes, password: str = "") -> pd.DataFrame:
    """Pull holdings out of a CAS PDF into :data:`EXTRACTED_COLUMNS`.

    Raises ``ValueError`` with a readable reason on a wrong password or a file
    the PDF reader cannot open, so the page can show it rather than crash.
    """
    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - the dependency is declared
        raise ValueError("Reading PDF statements needs the pdfplumber package.") from error

    rows: List[Dict[str, object]] = []
    try:
        with pdfplumber.open(io.BytesIO(data), password=password or None) as pdf:
            for page in pdf.pages:
                page_rows: List[Dict[str, object]] = []
                for table in page.extract_tables() or []:
                    page_rows.extend(_from_table(table))
                if not page_rows:
                    page_rows = _from_text(page.extract_text() or "")
                rows.extend(page_rows)
    except Exception as error:  # wrong password, corrupt file, unsupported PDF
        raise ValueError(_explain(error)) from error

    # No de-duplication by ISIN: the same stock held in two demat accounts is two
    # real positions, and the importer sums them per ISIN afterwards.
    return pd.DataFrame(rows, columns=list(EXTRACTED_COLUMNS))
