"""Tests for the depository CAS PDF import.

The fixtures are synthetic statements (see ``fixtures/holdings/make_cas_fixtures.py``
for how they are regenerated): one unlocked and one locked, each a holdings table
of ISIN / Security Name / Quantity / Price / Value.
"""

from pathlib import Path

import pytest

from utils import brokers, holdings
from utils.brokers import cas

FIXTURES = Path(__file__).parent / "fixtures" / "holdings"


@pytest.fixture(scope="module")
def master() -> holdings.SymbolMaster:
    return holdings.SymbolMaster.from_paths()


def pdf(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestExtraction:
    def test_reads_the_holdings_table(self):
        frame = cas.extract(pdf("cas.pdf"))
        assert list(frame.columns) == list(cas.EXTRACTED_COLUMNS)
        assert frame["ISIN"].tolist() == ["INE002A01018", "INE548A01028"]
        assert frame["Total Quantity"].tolist() == [10.0, 100.0]
        # Price is taken from the Value column when there is no price column.
        assert frame["Current Price"].tolist() == [2900.0, 90.0]

    def test_a_locked_statement_needs_its_password(self):
        with pytest.raises(ValueError, match="password-protected"):
            cas.extract(pdf("cas-locked.pdf"))

    def test_a_locked_statement_opens_with_its_password(self):
        frame = cas.extract(pdf("cas-locked.pdf"), password="secret")
        assert frame["ISIN"].tolist() == ["INE002A01018", "INE548A01028"]

    def test_a_non_pdf_raises_a_readable_error(self):
        with pytest.raises(ValueError, match="Could not read the statement"):
            cas.extract(b"%PDF-1.4 not really a pdf")

    def test_the_text_fallback_takes_the_isin_and_a_whole_quantity(self):
        rows = cas._from_text("INE002A01018 Reliance Industries Ltd 10 2,900.00")
        assert rows[0]["ISIN"] == "INE002A01018"
        assert rows[0]["Total Quantity"] == 10.0


class TestImport:
    def test_a_cas_is_read_as_a_statement(self, master):
        result = brokers.import_holdings(pdf("cas.pdf"), "cas.pdf", master=master)
        assert result.profile == "CAS"
        assert result.detected is True
        assert dict(zip(result.holdings["Symbol"], result.holdings["Total Quantity"])) == {
            "RELIANCE": 10.0,
            "HFCL": 100.0,
        }

    def test_the_missing_cost_basis_is_stated_not_hidden(self, master):
        result = brokers.import_holdings(pdf("cas.pdf"), "cas.pdf", master=master)
        assert any("no purchase price" in warning for warning in result.warnings)
        # No cost basis: value is the statement's, so P&L reads as flat.
        assert result.holdings["Unrealized P&L"].tolist() == [0.0, 0.0]

    def test_a_locked_statement_without_the_password_explains_itself(self, master):
        result = brokers.import_holdings(pdf("cas-locked.pdf"), "cas-locked.pdf", master=master)
        assert result.holdings.empty
        assert any("password-protected" in warning for warning in result.warnings)

    def test_a_locked_statement_imports_with_the_password(self, master):
        result = brokers.import_holdings(
            pdf("cas-locked.pdf"), "cas-locked.pdf", master=master, password="secret"
        )
        assert set(result.holdings["Symbol"]) == {"RELIANCE", "HFCL"}


if __name__ == "__main__":
    pytest.main([__file__])
