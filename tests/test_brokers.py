"""Tests for the broker import layer: detection, parsing, mapping and profiles."""

from pathlib import Path

import pandas as pd
import pytest

from utils import brokers, holdings
from utils.brokers import profiles as profile_library
from utils.brokers.base import find_signature_row

FIXTURES = Path(__file__).parent / "fixtures" / "holdings"


@pytest.fixture(scope="module")
def master() -> holdings.SymbolMaster:
    return holdings.SymbolMaster.from_paths()


def upload(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestDetection:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("zerodha.xlsx", "Zerodha"),
            ("groww.csv", "Groww"),
            ("dhan.csv", "Dhan"),
            ("angelone.csv", "Angel One"),
        ],
    )
    def test_each_fixture_is_claimed_by_its_broker(self, filename, expected):
        detected = brokers.detect_profile(upload(filename), filename)
        assert detected is not None
        assert detected.name == expected

    def test_a_plain_sheet_is_not_claimed(self):
        assert brokers.detect_profile(upload("unknown.csv"), "unknown.csv") is None

    def test_the_generic_profile_never_auto_detects(self):
        assert brokers.GENERIC.signature == ()


class TestZerodha:
    def test_sums_the_quantity_buckets(self, master):
        result = brokers.import_holdings(upload("zerodha.xlsx"), "zerodha.xlsx", master=master)
        assert result.profile == "Zerodha"
        assert result.detected is True
        quantities = dict(zip(result.holdings["Symbol"], result.holdings["Total Quantity"]))
        assert quantities == {"RELIANCE": 10.0, "HFCL": 120.0, "POLYCAB": 50.0}

    def test_values_follow_the_file_prices(self, master):
        result = brokers.import_holdings(upload("zerodha.xlsx"), "zerodha.xlsx", master=master)
        reliance = result.holdings.set_index("Symbol").loc["RELIANCE"]
        assert reliance["Invested Value"] == 25005.0
        assert reliance["Current Value"] == 29000.0

    def test_every_symbol_resolved(self, master):
        result = brokers.import_holdings(upload("zerodha.xlsx"), "zerodha.xlsx", master=master)
        assert result.summary["isin"] == 3
        assert result.summary["unresolved"] == 0


class TestOtherBrokers:
    def test_groww_resolves_from_isin(self, master):
        result = brokers.import_holdings(upload("groww.csv"), "groww.csv", master=master)
        assert result.profile == "Groww"
        assert set(result.holdings["Symbol"]) == {"RELIANCE", "TCS"}

    def test_dhan_reads_trading_symbol_and_cost(self, master):
        result = brokers.import_holdings(upload("dhan.csv"), "dhan.csv", master=master)
        assert result.profile == "Dhan"
        hfcl = result.holdings.set_index("Symbol").loc["HFCL"]
        assert hfcl["Total Quantity"] == 100.0
        assert hfcl["Invested Value"] == 8000.0

    def test_angel_one_reads_instrument_and_qty(self, master):
        result = brokers.import_holdings(upload("angelone.csv"), "angelone.csv", master=master)
        assert result.profile == "Angel One"
        assert dict(zip(result.holdings["Symbol"], result.holdings["Total Quantity"])) == {
            "POLYCAB": 50.0,
            "HFCL": 100.0,
        }


class TestGeneric:
    def test_unclaimed_file_falls_back_and_warns(self, master):
        result = brokers.import_holdings(upload("unknown.csv"), "unknown.csv", master=master)
        assert result.profile == "Generic"
        assert result.detected is False
        assert any("Could not tell which broker" in warning for warning in result.warnings)

    def test_a_saved_mapping_imports_odd_column_names(self, master, tmp_path):
        path = tmp_path / "odd.csv"
        path.write_text("Scrip,Qty,Buy Avg\nHFCL,100,80\n")
        profile = profile_library.profile_from_mapping(
            "Odd", {"Symbol": "Scrip", "Total Quantity": "Qty", "Average Price": "Buy Avg"}
        )
        result = brokers.import_holdings(path.read_bytes(), path.name, profile=profile, master=master)
        assert result.holdings["Symbol"].tolist() == ["HFCL"]
        assert result.holdings["Total Quantity"].tolist() == [100.0]

    def test_a_file_with_no_holdings_table_warns_gracefully(self, master):
        result = brokers.import_holdings(b"Foo,Bar\n1,2\n", "thing.csv", master=master)
        assert result.holdings.empty
        assert any("No holdings table" in warning for warning in result.warnings)


class TestTable:
    def test_finds_the_header_wherever_it_is(self):
        raw = brokers.read_raw(upload("zerodha.xlsx"), "zerodha.xlsx")
        assert find_signature_row(raw, brokers.PROFILES[0].signature) == 22

    def test_preview_table_keeps_the_broker_columns(self):
        table = brokers.preview_table(upload("zerodha.xlsx"), "zerodha.xlsx", brokers.PROFILES[0])
        assert "Quantity Available" in table.columns
        assert "Previous Closing Price" in table.columns

    def test_guess_mapping_suggests_known_aliases(self):
        table = pd.DataFrame(columns=["Stock Name", "ISIN", "Qty", "Average Price"])
        guessed = brokers.guess_mapping(table)
        assert guessed["Total Quantity"] == "Qty"
        assert guessed["Average Price"] == "Average Price"


class TestProfileLibrary:
    def test_save_and_list_round_trip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(profile_library, "PROFILE_DIR", tmp_path / "profiles")
        saved = profile_library.save_profile("My Broker", {"Symbol": "Scrip", "Total Quantity": "Qty"})
        assert saved is not None and saved.is_file()
        assert profile_library.saved_profiles() == {
            "My Broker": {"Symbol": "Scrip", "Total Quantity": "Qty"}
        }

    def test_empty_mapping_is_not_saved(self, monkeypatch, tmp_path):
        monkeypatch.setattr(profile_library, "PROFILE_DIR", tmp_path / "profiles")
        assert profile_library.save_profile("Empty", {}) is None


if __name__ == "__main__":
    pytest.main([__file__])
