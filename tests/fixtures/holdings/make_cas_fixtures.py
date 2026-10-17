"""Regenerate the CAS PDF fixtures in this folder.

The depository CAS statements the app parses are password-protected PDFs with a
holdings table. We cannot commit a real client statement, so these two synthetic
ones mirror the parts the extractor reads — an ``ISIN / Security Name / Quantity
/ Price / Value`` table — one unlocked and one locked.

Run with the dev dependency installed:

    uv run python tests/fixtures/holdings/make_cas_fixtures.py
"""

from pathlib import Path

from reportlab.lib import pdfencrypt
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

HERE = Path(__file__).resolve().parent

HEADER = ["ISIN", "Security Name", "Quantity", "Price", "Value"]
ROWS = [
    ["INE002A01018", "Reliance Industries Ltd", "10", "2,900.00", "29,000.00"],
    ["INE548A01028", "HFCL Ltd", "100", "90.00", "9,000.00"],
]


def build(path: Path, password: str | None = None) -> None:
    encrypt = pdfencrypt.StandardEncryption(password) if password else None
    document = SimpleDocTemplate(str(path), pagesize=A4, encrypt=encrypt)
    table = Table([HEADER, *ROWS], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    document.build(
        [table]
    )


if __name__ == "__main__":
    build(HERE / "cas.pdf")
    build(HERE / "cas-locked.pdf", password="secret")
    print("wrote", HERE / "cas.pdf", "and", HERE / "cas-locked.pdf")
