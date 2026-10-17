"""Tests for the Zerodha Kite Connect flow.

No network: every call goes through a fake transport, so the request headers,
the checksum body and the response handling are all inspected directly.
"""

import hashlib
import stat
from datetime import datetime, timezone

import pytest

from utils import brokers, holdings
from utils.brokers import api, kite


class FakeTransport:
    """Stands in for the HTTP call, recording what it was asked to send."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, method, url, body, headers):
        self.calls.append({"method": method, "url": url, "body": body, "headers": headers})
        return self.payload


CONFIG = kite.KiteConfig(api_key="key", api_secret="secret")
SESSION = kite.KiteSession(api_key="key", access_token="tok", user_id="AB1234")


def success(data):
    return {"status": "success", "data": data}


class TestConfig:
    def test_reads_the_secrets_table(self):
        config = kite.KiteConfig.from_secrets(
            {"kite": {"api_key": "k", "api_secret": "s", "redirect_url": "https://x"}}
        )
        assert (config.api_key, config.api_secret, config.redirect_url) == ("k", "s", "https://x")
        assert config.configured

    def test_falls_back_to_the_environment(self, monkeypatch):
        monkeypatch.setenv("KITE_API_KEY", "ek")
        monkeypatch.setenv("KITE_API_SECRET", "es")
        assert kite.KiteConfig.from_secrets({}).api_key == "ek"

    def test_unconfigured_without_credentials(self):
        assert not kite.KiteConfig().configured

    def test_login_url_carries_the_app_key(self):
        url = kite.KiteConfig(api_key="k").login_url()
        assert url.startswith("https://kite.trade/connect/login?")
        assert "api_key=k" in url and "v=3" in url


class TestChecksum:
    def test_matches_the_documented_sha256(self):
        expected = hashlib.sha256(b"keyrequesttokensecret").hexdigest()
        assert kite.checksum("key", "requesttoken", "secret") == expected

    def test_changes_with_any_input(self):
        assert kite.checksum("key", "rt", "secret") != kite.checksum("key", "rt2", "secret")


class TestSession:
    def test_a_morning_token_expires_the_same_day(self):
        # 00:00 UTC is 05:30 IST, before the 07:30 reset.
        session = kite.KiteSession("key", "tok", generated_at=datetime(2026, 1, 1, 0, tzinfo=timezone.utc))
        expiry = session.expires_at()
        assert (expiry.date().isoformat(), expiry.strftime("%H:%M")) == ("2026-01-01", "07:30")

    def test_an_evening_token_expires_the_next_morning(self):
        # 03:00 UTC is 08:30 IST, after the reset.
        session = kite.KiteSession("key", "tok", generated_at=datetime(2026, 1, 1, 3, tzinfo=timezone.utc))
        assert session.expires_at().date().isoformat() == "2026-01-02"

    def test_freshness_tracks_the_reset(self):
        session = kite.KiteSession("key", "tok", generated_at=datetime(2026, 1, 1, 0, tzinfo=timezone.utc))
        assert session.is_fresh(datetime(2026, 1, 1, 1, tzinfo=timezone.utc))
        assert not session.is_fresh(datetime(2026, 1, 1, 3, tzinfo=timezone.utc))


class TestTokenStore:
    def test_round_trip(self, tmp_path):
        store = kite.TokenStore(tmp_path)
        store.save(SESSION)
        loaded = store.load()
        assert loaded is not None
        assert (loaded.api_key, loaded.access_token, loaded.user_id) == ("key", "tok", "AB1234")

    def test_the_token_file_is_owner_readable_only(self, tmp_path):
        path = kite.TokenStore(tmp_path).save(SESSION)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_clear_removes_it(self, tmp_path):
        store = kite.TokenStore(tmp_path)
        store.save(SESSION)
        store.clear()
        assert store.load() is None

    def test_missing_file_loads_as_none(self, tmp_path):
        assert kite.TokenStore(tmp_path).load() is None

    def test_current_session_ignores_a_stale_token(self, tmp_path):
        store = kite.TokenStore(tmp_path)
        store.save(SESSION)  # generated now
        later = datetime(2099, 1, 1, tzinfo=timezone.utc)
        assert kite.current_session(store) is not None
        assert kite.current_session(store, now=later) is None


class TestExchange:
    def test_refuses_without_configured_credentials(self):
        with pytest.raises(api.NotConfigured):
            kite.exchange_request_token(kite.KiteConfig(), "rt")

    def test_refuses_without_a_request_token(self):
        with pytest.raises(ValueError, match="request_token"):
            kite.exchange_request_token(CONFIG, "")

    def test_posts_the_key_token_and_checksum(self):
        transport = FakeTransport(success({"access_token": "tok", "user_id": "AB1234"}))
        session = kite.exchange_request_token(CONFIG, "rt", transport=transport)

        call = transport.calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/session/token")
        body = call["body"].decode()
        assert "api_key=key" in body and "request_token=rt" in body
        assert f"checksum={kite.checksum('key', 'rt', 'secret')}" in body
        assert session.access_token == "tok" and session.user_id == "AB1234"

    def test_surfaces_kites_own_error(self):
        transport = FakeTransport({"status": "error", "message": "Token is invalid"})
        with pytest.raises(ValueError, match="Token is invalid"):
            kite.exchange_request_token(CONFIG, "rt", transport=transport)

    def test_a_reply_without_a_token_is_an_error(self):
        transport = FakeTransport(success({"user_id": "AB1234"}))
        with pytest.raises(ValueError, match="access token"):
            kite.exchange_request_token(CONFIG, "rt", transport=transport)


class TestHoldings:
    def test_sends_the_token_header_and_normalises(self):
        transport = FakeTransport(
            success(
                [
                    {
                        "tradingsymbol": "RELIANCE",
                        "isin": "INE002A01018",
                        "quantity": 10,
                        "average_price": 2500.5,
                        "last_price": 2900.0,
                    }
                ]
            )
        )
        frame = kite.fetch_holdings(SESSION, transport=transport)
        call = transport.calls[0]
        assert call["headers"]["Authorization"] == "token key:tok"
        assert call["url"].endswith("/portfolio/holdings")
        assert frame.iloc[0]["Symbol"] == "RELIANCE"
        assert frame.iloc[0]["Total Quantity"] == 10

    def test_surfaces_an_expired_token(self):
        transport = FakeTransport({"status": "error", "message": "Token is invalid or has expired"})
        with pytest.raises(ValueError, match="expired"):
            kite.fetch_holdings(SESSION, transport=transport)

    def test_a_kite_frame_lands_on_the_same_canonical_schema(self):
        transport = FakeTransport(
            success(
                [
                    {
                        "tradingsymbol": "WRONG",
                        "isin": "INE455K01017",  # Polycab: the ISIN must win
                        "quantity": 5,
                        "average_price": 100,
                        "last_price": 120,
                    }
                ]
            )
        )
        frame = kite.fetch_holdings(SESSION, transport=transport)
        result = brokers.import_records(
            frame,
            profile_name="Zerodha (Kite Connect)",
            source="AB1234",
            master=holdings.SymbolMaster.from_paths(),
        )
        assert result.holdings.iloc[0]["Symbol"] == "POLYCAB"
        assert result.holdings.iloc[0]["Invested Value"] == 500.0
        assert result.detected is True


if __name__ == "__main__":
    pytest.main([__file__])
