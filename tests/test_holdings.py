"""Pure tests for the canonical holdings schema and the symbol resolver."""

import pandas as pd
import pytest

from utils import holdings


def sample_master() -> holdings.SymbolMaster:
    sectors = pd.DataFrame(
        {
            "Company": ["Reliance Industries Ltd.", "Polycab India Ltd.", "Foo Steel Ltd.", "Foo Cement Ltd."],
            "NSE code": ["RELIANCE", "POLYCAB", "FOOSTEEL", "FOOCEM"],
            "ISIN": ["INE002A01018", "INE455K01017", "INE000A01011", "INE000A01029"],
            "Sector": ["Oil & Gas", "Industrials", "Steel", "Cement"],
        }
    )
    return holdings.SymbolMaster.from_frames(sectors)


class TestSymbols:
    def test_normalize_symbol_strips_series_and_exchange_prefixes(self):
        assert holdings.normalize_symbol("reliance-eq") == "RELIANCE"
        assert holdings.normalize_symbol(" NSE:TCS ") == "TCS"
        assert holdings.normalize_symbol("HFCL.NS") == "HFCL"

    def test_normalize_symbol_keeps_genuine_punctuation(self):
        assert holdings.normalize_symbol("M&M") == "M&M"
        assert holdings.normalize_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO"

    def test_normalize_symbol_rejects_blanks(self):
        assert holdings.normalize_symbol(None) == ""
        assert holdings.normalize_symbol(" nan ") == ""
        assert holdings.normalize_symbol("-") == ""

    def test_is_isin(self):
        assert holdings.is_isin("INE002A01018")
        assert not holdings.is_isin("RELIANCE")
        assert not holdings.is_isin("INE002A0101")


class TestMaster:
    def test_indexes_isin_symbol_name_and_sector(self):
        master = sample_master()
        assert master.by_isin["INE002A01018"] == "RELIANCE"
        assert master.by_symbol["POLYCAB"] == "POLYCAB"
        assert master.by_name["RELIANCE INDUSTRIES"] == "RELIANCE"
        assert master.sector("RELIANCE") == "Oil & Gas"

    def test_empty_master_is_falsy(self):
        assert not holdings.SymbolMaster()


class TestResolver:
    def test_isin_wins_over_a_wrong_file_symbol(self):
        resolution = holdings.resolve_one(
            isin="INE455K01017", symbol="WRONG", master=sample_master()
        )
        assert resolution == holdings.Resolution("POLYCAB", "isin")

    def test_symbol_match_when_there_is_no_isin(self):
        resolution = holdings.resolve_one(symbol="reliance-eq", master=sample_master())
        assert resolution.status == "symbol"
        assert resolution.symbol == "RELIANCE"

    def test_name_match(self):
        resolution = holdings.resolve_one(name="Reliance Industries Ltd.", master=sample_master())
        assert resolution == holdings.Resolution("RELIANCE", "name")

    def test_alias_overrides_everything(self):
        resolution = holdings.resolve_one(
            isin="INE002A01018",
            symbol="RELIANCE",
            master=sample_master(),
            aliases={"reliance": "POLYCAB"},
        )
        assert resolution == holdings.Resolution("POLYCAB", "alias")

    def test_ambiguous_name_is_surfaced_not_guessed(self):
        resolution = holdings.resolve_one(name="Foo Ltd", master=sample_master())
        assert resolution.status == "ambiguous"
        assert set(resolution.candidates) == {"FOOCEM", "FOOSTEEL"}

    def test_unknown_row_keeps_the_cleaned_symbol(self):
        resolution = holdings.resolve_one(symbol="BRANDNEW", master=sample_master())
        assert resolution.status == "unresolved"
        assert resolution.symbol == "BRANDNEW"

    def test_resolve_adds_symbol_and_match(self):
        frame = pd.DataFrame(
            {
                "Symbol": ["", "POLYCAB", "NOPE"],
                "ISIN": ["INE002A01018", "", ""],
                "Company": ["", "", ""],
            }
        )
        resolved = holdings.resolve(frame, sample_master())
        assert resolved["Symbol"].tolist() == ["RELIANCE", "POLYCAB", "NOPE"]
        assert resolved["Match"].tolist() == ["isin", "symbol", "unresolved"]
        assert holdings.match_summary(resolved)["unresolved"] == 1


class TestValues:
    def test_derive_values_multiplies_quantity_by_price(self):
        frame = pd.DataFrame(
            {
                "Symbol": ["RELIANCE"],
                "Total Quantity": [10],
                "Average Price": [2500.0],
                "Current Price": [2900.0],
            }
        )
        derived = holdings.derive_values(frame)
        row = derived.iloc[0]
        assert row["Invested Value"] == 25000.0
        assert row["Current Value"] == 29000.0
        assert row["Unrealized P&L"] == 4000.0

    def test_price_lookup_overrides_the_file_price(self):
        frame = pd.DataFrame(
            {"Symbol": ["RELIANCE"], "Total Quantity": [10], "Average Price": [2500.0], "Current Price": [2900.0]}
        )
        derived = holdings.derive_values(frame, prices={"RELIANCE": 3000.0})
        assert derived.iloc[0]["Current Price"] == 3000.0
        assert derived.iloc[0]["Current Value"] == 30000.0

    def test_missing_price_falls_back_to_cost_basis(self):
        frame = pd.DataFrame({"Symbol": ["RELIANCE"], "Total Quantity": [2], "Average Price": [100.0]})
        derived = holdings.derive_values(frame)
        assert derived.iloc[0]["Current Value"] == 200.0
        assert derived.iloc[0]["Unrealized P&L"] == 0.0

    def test_formatted_numbers_are_parsed(self):
        frame = pd.DataFrame(
            {"Symbol": ["A"], "Total Quantity": ["1,000"], "Average Price": ["₹1,234.50"], "Current Price": ["(20)"]}
        )
        derived = holdings.derive_values(frame)
        assert derived.iloc[0]["Total Quantity"] == 1000.0
        assert derived.iloc[0]["Average Price"] == 1234.50

    def test_to_core_keeps_four_columns_and_drops_blank_symbols(self):
        frame = pd.DataFrame(
            {
                "Symbol": ["RELIANCE", ""],
                "Total Quantity": [1, 2],
                "Invested Value": [1.0, 2.0],
                "Current Value": [1.0, 2.0],
            }
        )
        core = holdings.to_core(frame)
        assert list(core.columns) == list(holdings.CORE_COLUMNS)
        assert core["Symbol"].tolist() == ["RELIANCE"]


class TestMerge:
    def test_same_isin_across_brokers_collapses_to_one_position(self):
        rows = pd.DataFrame(
            {
                "Client": ["Me", "Me"],
                "Broker": ["Zerodha", "Groww"],
                "Source": ["z.xlsx", "g.csv"],
                "Symbol": ["RELIANCE", "RELIANCE"],
                "ISIN": ["INE002A01018", "INE002A01018"],
                "Total Quantity": [10, 10],
                "Average Price": [100.0, 200.0],
                "Current Price": [150.0, 150.0],
            }
        )
        derived = holdings.derive_values(rows)
        merged = holdings.merge_positions(derived)
        assert len(merged) == 1
        position = merged.iloc[0]
        assert position["Total Quantity"] == 20
        assert position["Average Price"] == 150.0  # value-weighted
        assert position["Broker"] == "Groww+Zerodha"
        assert position["Invested Value"] == 3000.0

    def test_different_clients_stay_apart(self):
        rows = pd.DataFrame(
            {
                "Client": ["A", "B"],
                "Symbol": ["RELIANCE", "RELIANCE"],
                "ISIN": ["INE002A01018", "INE002A01018"],
                "Total Quantity": [1, 2],
                "Average Price": [10.0, 10.0],
                "Current Price": [10.0, 10.0],
            }
        )
        merged = holdings.merge_positions(holdings.derive_values(rows))
        assert sorted(merged["Client"]) == ["A", "B"]


class TestPriceLookup:
    def test_last_close_per_symbol(self):
        prices = pd.DataFrame(
            {"RELIANCE": [10.0, 12.0], "HFCL": [1.0, None]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        lookup = holdings.price_lookup(prices)
        assert lookup == {"RELIANCE": 12.0, "HFCL": 1.0}

    def test_empty_prices(self):
        assert holdings.price_lookup(pd.DataFrame()) == {}


if __name__ == "__main__":
    pytest.main([__file__])
