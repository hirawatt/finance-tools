"""Tests for the consented broker-API layer.

Nothing here touches the network: the request a call *would* make is built and
inspected, and the response *shapes* are the ones the brokers document.
"""

import pytest

from utils import holdings
from utils.brokers import api


class TestRegistry:
    def test_covers_the_agreed_brokers(self):
        assert set(api.PROVIDERS_BY_NAME) == {"Zerodha", "Upstox", "Dhan", "Angel One"}

    def test_every_provider_documents_itself(self):
        for provider in api.PROVIDERS:
            assert provider.docs.startswith("https://")
            assert provider.holdings_url.startswith("https://")
            assert provider.record_aliases

    def test_unconfirmed_field_names_say_so(self):
        assert "confirm" in api.PROVIDERS_BY_NAME["Dhan"].note.lower()
        assert "confirm" in api.PROVIDERS_BY_NAME["Angel One"].note.lower()


class TestRequest:
    def test_zerodha_carries_the_app_key_and_token(self):
        headers = api.PROVIDERS_BY_NAME["Zerodha"].headers("tok", api_key="key")
        assert headers["Authorization"] == "token key:tok"

    def test_upstox_uses_a_bearer_token(self):
        headers = api.PROVIDERS_BY_NAME["Upstox"].headers("tok")
        assert headers["Authorization"] == "Bearer tok"

    def test_dhan_uses_its_own_header(self):
        headers = api.PROVIDERS_BY_NAME["Dhan"].headers("tok")
        assert headers["access-token"] == "tok"

    def test_a_call_without_a_token_is_refused(self):
        provider = api.PROVIDERS_BY_NAME["Upstox"]
        with pytest.raises(api.NotConfigured):
            api.build_request(provider, token="")

    def test_angel_one_posts_a_json_body(self):
        provider = api.PROVIDERS_BY_NAME["Angel One"]
        url, headers, body = api.build_request(provider, "tok")
        assert provider.method == "POST"
        assert body == b"{}"
        assert headers["Content-Type"] == "application/json"


class TestNormalise:
    def test_unwraps_the_documented_envelopes(self):
        provider = api.PROVIDERS_BY_NAME["Zerodha"]
        assert api.records_from_payload(provider, {"data": [{"isin": "X"}]}) == [{"isin": "X"}]
        assert api.records_from_payload(provider, [{"isin": "Y"}]) == [{"isin": "Y"}]
        angel = api.PROVIDERS_BY_NAME["Angel One"]
        assert api.records_from_payload(angel, {"data": {"holdings": [{"isin": "Z"}]}}) == [
            {"isin": "Z"}
        ]
        assert api.records_from_payload(provider, {"status": "error"}) == []

    def test_maps_a_zerodha_record_to_the_canonical_columns(self):
        provider = api.PROVIDERS_BY_NAME["Zerodha"]
        frame = provider.normalise(
            [
                {
                    "tradingsymbol": "RELIANCE",
                    "isin": "INE002A01018",
                    "quantity": 10,
                    "average_price": 2500.5,
                    "last_price": 2900.0,
                    "pnl": 3995.0,
                }
            ]
        )
        row = frame.iloc[0]
        assert row["Symbol"] == "RELIANCE"
        assert row["Total Quantity"] == 10
        assert row["Average Price"] == 2500.5
        assert row["Broker"] == "Zerodha"

    def test_maps_dhan_style_keys_through_the_aliases(self):
        provider = api.PROVIDERS_BY_NAME["Dhan"]
        frame = provider.normalise(
            [{"tradingSymbol": "HFCL", "isin": "INE548A01028", "totalQty": 100, "avgCostPrice": 80, "lastTradedPrice": 90}]
        )
        row = frame.iloc[0]
        assert row["Symbol"] == "HFCL"
        assert row["Total Quantity"] == 100
        assert row["Average Price"] == 80

    def test_a_normalised_frame_feeds_the_same_pipeline_as_a_file(self):
        provider = api.PROVIDERS_BY_NAME["Upstox"]
        frame = provider.normalise(
            [{"tradingsymbol": "WRONG", "isin": "INE455K01017", "quantity": 5, "average_price": 100, "last_price": 120}]
        )
        master = holdings.SymbolMaster.from_paths()
        resolved = holdings.resolve(frame, master)
        derived = holdings.derive_values(resolved)
        assert derived.iloc[0]["Symbol"] == "POLYCAB"  # ISIN wins over the broker's symbol
        assert derived.iloc[0]["Invested Value"] == 500.0

    def test_empty_payload_yields_an_empty_frame(self):
        frame = api.PROVIDERS_BY_NAME["Zerodha"].normalise([])
        assert frame.empty
        assert "Symbol" in frame.columns


if __name__ == "__main__":
    pytest.main([__file__])
