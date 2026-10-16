"""Tests for utils.snapshot.

Everything here runs offline: object storage is exercised through a fake client
or a :class:`~utils.snapshot.LocalStore` in ``tmp_path``, and every live network
entry point is monkeypatched.
"""

from __future__ import annotations

import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from utils import snapshot

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 15)
REPO_ROOT = Path(__file__).resolve().parent.parent
CO_PILOT = REPO_ROOT / "pages" / "portfolio_analysis.py"


@pytest.fixture
def store(tmp_path):
    return snapshot.LocalStore(tmp_path / "snapshots")


@pytest.fixture(autouse=True)
def clean_snapshot_env(monkeypatch):
    """Keep the host environment from leaking into config resolution."""
    for name in (
        "SNAPSHOT_BUCKET", "SNAPSHOT_PREFIX", "SNAPSHOT_DIR", "SNAPSHOT_ENDPOINT_URL",
        "SNAPSHOT_REGION", "SNAPSHOT_ACCESS_KEY", "SNAPSHOT_SECRET_KEY",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _forbid_live():
    def boom(*args, **kwargs):
        raise AssertionError("the live provider must not be called")

    return boom


def _business_days(periods: int = 300) -> pd.DatetimeIndex:
    # Matches what yfinance returns: a DatetimeIndex named "Date".
    return pd.date_range("2026-01-01", periods=periods, freq="B", name="Date")


def _prices(columns=("AAA", "BBB"), periods: int = 300) -> pd.DataFrame:
    index = _business_days(periods)
    return pd.DataFrame(
        {name: np.linspace(100.0, 200.0, periods) + offset
         for offset, name in enumerate(columns)},
        index=index,
    )


def _write_holdings(path, symbols, extra_columns: int = 8):
    """Write a Zerodha-shaped sheet: header on row 23, spanning columns B..L."""
    frame = pd.DataFrame(
        {f"Quantity {i}": [0.0] * len(symbols) for i in range(extra_columns)}
    )
    frame.insert(0, "Symbol", list(symbols))
    frame["Average Price"] = 100.0
    frame["Previous Closing Price"] = 110.0
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, index=False, startrow=22, startcol=1)
    return path


def _seed(store, *, generated_at=None, failures=None, **frames):
    flat = {}
    for name, frame in frames.items():
        if frame is None:
            continue
        flat[name] = frame.reset_index() if frame.index.name else frame
    return snapshot.write_snapshot(
        store,
        flat,
        generated_at=generated_at or NOW,
        universe=["AAA"],
        failures=failures,
    )


# --------------------------------------------------------------------------- #
# Universe
# --------------------------------------------------------------------------- #
class TestUniverse:
    def test_index_dir_reads_first_row_of_each_file(self, tmp_path):
        (tmp_path / "a.csv").write_text("polycab,HFCL\n")
        (tmp_path / "b.csv").write_text("hudco\n")
        (tmp_path / "empty.csv").write_text("")
        (tmp_path / "notes.txt").write_text("ignored")

        assert snapshot.symbols_from_index_dir(tmp_path) == ["POLYCAB", "HFCL", "HUDCO"]

    def test_holdings_are_uppercased(self, tmp_path):
        path = _write_holdings(tmp_path / "holdings.xlsx", ["polycab", "HFCL"])
        assert snapshot.symbols_from_holdings(path) == ["POLYCAB", "HFCL"]

    def test_holdings_without_a_symbol_column_is_empty(self, tmp_path):
        path = tmp_path / "holdings.xlsx"
        frame = pd.DataFrame({f"Quantity {i}": [1.0] for i in range(11)})
        with pd.ExcelWriter(path) as writer:
            frame.to_excel(writer, index=False, startrow=22, startcol=1)
        assert snapshot.symbols_from_holdings(path) == []

    def test_build_universe_unions_and_dedupes(self, tmp_path):
        index_dir = tmp_path / "indices"
        index_dir.mkdir()
        (index_dir / "a.csv").write_text("hfcl,POLYCAB\n")
        (index_dir / "b.csv").write_text("POLYCAB\n")
        holdings = _write_holdings(tmp_path / "h.xlsx", ["HUDCO"])

        assert snapshot.build_universe(index_dir, holdings) == ["HFCL", "HUDCO", "POLYCAB"]


# --------------------------------------------------------------------------- #
# Frame conversions
# --------------------------------------------------------------------------- #
class TestPriceFrames:
    def test_round_trip_including_benchmark(self):
        prices = _prices(periods=5)
        benchmark = pd.Series(
            np.linspace(1000, 1100, 5), index=prices.index, name="NIFTY 50"
        )

        wide, series = snapshot.frame_to_prices(snapshot.prices_to_frame(prices, benchmark))

        # check_freq=False: the fixture index carries a business-day freq that a
        # real (gappy) trading calendar does not.
        pd.testing.assert_frame_equal(wide, prices, check_freq=False)
        assert series is not None
        assert series.name == "NIFTY 50"
        np.testing.assert_allclose(series.to_numpy(), benchmark.to_numpy())

    def test_nan_gaps_are_dropped_not_stored(self):
        prices = _prices(periods=5)
        prices.iloc[0, 0] = np.nan

        frame = snapshot.prices_to_frame(prices, None)

        assert not frame["Close"].isna().any()
        assert len(frame) == len(prices) * 2 - 1

    def test_benchmark_is_not_a_column_of_the_wide_frame(self):
        frame = snapshot.prices_to_frame(_prices(periods=3), None)
        frame = pd.concat(
            [
                frame,
                pd.DataFrame(
                    {"Date": _business_days(3), "Symbol": snapshot.BENCHMARK_KEY, "Close": 1.0}
                ),
            ],
            ignore_index=True,
        )
        wide, benchmark = snapshot.frame_to_prices(frame)
        assert snapshot.BENCHMARK_KEY not in wide.columns
        assert benchmark is not None

    def test_empty_inputs(self):
        assert snapshot.prices_to_frame(None, None).empty
        wide, benchmark = snapshot.frame_to_prices(pd.DataFrame())
        assert wide.empty and benchmark is None
        wide, benchmark = snapshot.frame_to_prices(pd.DataFrame({"nonsense": [1]}))
        assert wide.empty and benchmark is None


class TestEarningsFrames:
    def test_stores_the_date_not_days_away(self):
        frame = pd.DataFrame(
            [{"Symbol": "AAA", "Date": date(2026, 11, 5), "Days away": 21,
              "EPS estimate": 1.0, "Revenue estimate": 2.0}]
        )
        stored = snapshot.earnings_to_frame(frame)
        assert "Days away" not in stored.columns
        assert stored.loc[0, "Date"] == "2026-11-05"

    def test_read_recomputes_days_away(self):
        stored = pd.DataFrame(
            [{"Symbol": "AAA", "Date": "2026-11-05", "EPS estimate": 1.0,
              "Revenue estimate": 2.0}]
        )
        out = snapshot.frame_to_earnings(stored, today=TODAY)
        assert list(out.columns) == snapshot.EARNINGS_COLUMNS
        assert out.loc[0, "Days away"] == 21

    def test_read_drops_dates_that_have_passed(self):
        stored = pd.DataFrame(
            [{"Symbol": "AAA", "Date": "2026-01-01", "EPS estimate": None,
              "Revenue estimate": None}]
        )
        assert snapshot.frame_to_earnings(stored, today=TODAY).empty

    def test_empty(self):
        assert snapshot.earnings_to_frame(None).empty
        assert snapshot.frame_to_earnings(None).empty


# --------------------------------------------------------------------------- #
# Storage and configuration
# --------------------------------------------------------------------------- #
class TestLocalStore:
    def test_missing_blob_is_none(self, tmp_path):
        assert snapshot.LocalStore(tmp_path).read("nope.parquet") is None

    def test_write_then_read(self, tmp_path):
        store = snapshot.LocalStore(tmp_path / "nested")
        store.write("a.bin", b"payload")
        assert store.read("a.bin") == b"payload"

    def test_write_leaves_no_temporary_file(self, tmp_path):
        store = snapshot.LocalStore(tmp_path)
        store.write("a.bin", b"payload")
        assert [p.name for p in tmp_path.iterdir()] == ["a.bin"]


class TestS3Store:
    def test_uses_the_prefix_and_round_trips_bytes(self):
        client = MagicMock()
        store = snapshot.S3Store("bucket", "snapshots", client=client)

        store.write("prices.parquet", b"data")
        client.put_object.assert_called_once_with(
            Bucket="bucket", Key="snapshots/prices.parquet", Body=b"data"
        )

        client.get_object.return_value = {"Body": MagicMock(read=lambda: b"data")}
        assert store.read("prices.parquet") == b"data"
        client.get_object.assert_called_once_with(
            Bucket="bucket", Key="snapshots/prices.parquet"
        )

    def test_blank_prefix_does_not_lead_with_a_slash(self):
        client = MagicMock()
        snapshot.S3Store("bucket", "", client=client).write("m.json", b"{}")
        assert client.put_object.call_args.kwargs["Key"] == "m.json"

    def test_read_failure_is_a_miss(self):
        client = MagicMock()
        client.get_object.side_effect = RuntimeError("NoSuchKey")
        assert snapshot.S3Store("bucket", client=client).read("m.json") is None


class TestConfig:
    def test_without_configuration_uses_a_local_directory(self):
        config = snapshot.SnapshotConfig.from_env({})
        assert config.uses_object_storage is False
        assert isinstance(config.store(), snapshot.LocalStore)

    def test_local_dir_override(self, tmp_path):
        config = snapshot.SnapshotConfig.from_env({"SNAPSHOT_DIR": str(tmp_path)})
        assert config.store().root == tmp_path

    def test_env_is_read_including_aws_fallbacks(self):
        config = snapshot.SnapshotConfig.from_env(
            {
                "SNAPSHOT_BUCKET": "b",
                "SNAPSHOT_ENDPOINT_URL": "https://r2.example.com",
                "SNAPSHOT_REGION": "auto",
                "AWS_ACCESS_KEY_ID": "key",
                "AWS_SECRET_ACCESS_KEY": "secret",
            }
        )
        assert config.uses_object_storage is True
        assert config.endpoint_url == "https://r2.example.com"
        assert config.region == "auto"
        assert config.access_key == "key"
        assert config.secret_key == "secret"

    def test_secrets_table_wins_over_the_environment(self):
        config = snapshot.SnapshotConfig.from_mapping(
            {"bucket": "from-secrets"}, {"SNAPSHOT_BUCKET": "from-env"}
        )
        assert config.bucket == "from-secrets"

    def test_blank_secrets_fall_back_to_the_environment(self):
        config = snapshot.SnapshotConfig.from_mapping(
            {"bucket": ""}, {"SNAPSHOT_BUCKET": "from-env"}
        )
        assert config.bucket == "from-env"

    def test_from_secrets_reads_the_snapshot_table(self):
        config = snapshot.SnapshotConfig.from_secrets(
            {"snapshot": {"bucket": "b", "prefix": "nightly"}}
        )
        assert config.bucket == "b"
        assert config.prefix == "nightly"

    def test_from_secrets_tolerates_no_table(self):
        assert snapshot.SnapshotConfig.from_secrets({}).bucket is None
        assert snapshot.SnapshotConfig.from_secrets(None).bucket is None

    def test_unknown_secret_keys_are_ignored(self):
        config = snapshot.SnapshotConfig.from_mapping({"bucket": "b", "banana": "x"})
        assert config.bucket == "b"


# --------------------------------------------------------------------------- #
# Freshness and manifest
# --------------------------------------------------------------------------- #
class TestFreshness:
    def test_fresh_within_the_window(self):
        assert snapshot.is_fresh({"generated_at": (NOW - timedelta(hours=1)).isoformat()}, now=NOW)

    def test_stale_outside_the_window(self):
        stamp = (NOW - snapshot.DEFAULT_MAX_AGE - timedelta(minutes=1)).isoformat()
        assert not snapshot.is_fresh({"generated_at": stamp}, now=NOW)

    def test_small_clock_skew_is_tolerated(self):
        assert snapshot.is_fresh({"generated_at": (NOW + timedelta(minutes=10)).isoformat()}, now=NOW)

    def test_naive_timestamps_are_treated_as_utc(self):
        assert snapshot.is_fresh({"generated_at": "2026-10-15T11:00:00"}, now=NOW)

    def test_missing_or_unusable_manifests(self):
        assert not snapshot.is_fresh(None, now=NOW)
        assert not snapshot.is_fresh({}, now=NOW)
        assert not snapshot.is_fresh({"generated_at": "not a date"}, now=NOW)
        assert not snapshot.is_fresh({"generated_at": 42}, now=NOW)


class TestWriteAndRead:
    def test_round_trip(self, store):
        _seed(store, prices=snapshot.prices_to_frame(_prices(periods=5), None))

        loaded = snapshot.read_snapshot(store, now=NOW)

        assert loaded is not None
        assert set(loaded.frames) == {"prices"}
        assert loaded.manifest["benchmark"] == snapshot.BENCHMARK_KEY
        assert loaded.manifest["universe_size"] == 1

    def test_manifest_records_rows_and_failures(self, store):
        manifest = _seed(
            store,
            prices=snapshot.prices_to_frame(_prices(periods=5), None),
            failures={"surveillance": ["RuntimeError: nse down"]},
        )
        assert manifest["datasets"]["prices"]["rows"] == 10
        assert manifest["failures"]["surveillance"] == ["RuntimeError: nse down"]

    def test_manifest_is_written_last(self):
        written = []

        class Recorder:
            def read(self, name):
                return None

            def write(self, name, payload):
                written.append(name)

        snapshot.write_snapshot(
            Recorder(), {"prices": pd.DataFrame(columns=snapshot.PRICE_COLUMNS)}
        )
        assert written[-1] == snapshot.MANIFEST_NAME

    def test_stale_snapshot_is_not_read(self, store):
        _seed(store, generated_at=NOW - timedelta(days=4), prices=pd.DataFrame(columns=snapshot.PRICE_COLUMNS))
        assert snapshot.read_snapshot(store, now=NOW) is None

    def test_absent_snapshot_is_not_read(self, store):
        assert snapshot.read_snapshot(store, now=NOW) is None

    def test_corrupt_manifest_is_not_read(self, store):
        store.write(snapshot.MANIFEST_NAME, b"{not json")
        assert snapshot.read_snapshot(store, now=NOW) is None

    def test_a_failed_blob_does_not_lose_the_others(self, store):
        _seed(
            store,
            prices=snapshot.prices_to_frame(_prices(periods=5), None),
            company_data=pd.DataFrame({"Symbol": ["AAA"], "Market cap": [1.0]}).set_index("Symbol"),
        )
        store.write("company_data.parquet", b"corrupt")

        loaded = snapshot.read_snapshot(store, now=NOW)
        assert loaded is not None
        assert set(loaded.frames) == {"prices"}


# --------------------------------------------------------------------------- #
# Read-through helpers
# --------------------------------------------------------------------------- #
class TestLoadPrices:
    def test_serves_from_the_snapshot_without_touching_the_provider(self, store, monkeypatch):
        _seed(store, prices=snapshot.prices_to_frame(_prices(), None))
        monkeypatch.setattr(snapshot, "fetch_price_history", _forbid_live())

        prices, benchmark = snapshot.load_prices(["AAA", "BBB"], period="1y", store=store, now=NOW)

        assert list(prices.columns) == ["AAA", "BBB"]
        assert benchmark is None

    def test_slices_the_requested_period(self, store):
        _seed(store, prices=snapshot.prices_to_frame(_prices(), None))

        long_window, _ = snapshot.load_prices(["AAA"], period="2y", store=store, now=NOW)
        short_window, _ = snapshot.load_prices(["AAA"], period="6mo", store=store, now=NOW)

        assert 0 < len(short_window) < len(long_window) <= 300
        assert long_window.index.is_monotonic_increasing

    def test_matches_symbols_case_insensitively_and_keeps_the_requested_spelling(self, store):
        _seed(store, prices=snapshot.prices_to_frame(_prices(columns=["AAA"]), None))
        prices, _ = snapshot.load_prices(["aaa"], period="1y", store=store, now=NOW)
        assert list(prices.columns) == ["aaa"]

    def test_fetches_only_uncovered_symbols(self, store, monkeypatch):
        _seed(store, prices=snapshot.prices_to_frame(_prices(columns=["AAA"]), None))
        calls = {}

        def fake_live(symbols, period="1y", benchmark=None):
            calls["symbols"] = list(symbols)
            calls["benchmark"] = benchmark
            return pd.DataFrame({"ZZZ": [1.0, 2.0]}, index=_business_days(2)), None

        monkeypatch.setattr(snapshot, "fetch_price_history", fake_live)
        prices, _ = snapshot.load_prices(["AAA", "ZZZ"], period="1y", store=store, now=NOW)

        assert calls["symbols"] == ["ZZZ"]
        assert calls["benchmark"] is None  # the benchmark comes from the snapshot
        assert set(prices.columns) == {"AAA", "ZZZ"}

    def test_benchmark_travels_with_the_snapshot(self, store, monkeypatch):
        monkeypatch.setattr(snapshot, "fetch_price_history", _forbid_live())
        index = _business_days(10)
        benchmark = pd.Series(np.linspace(1000, 1100, 10), index=index, name="NIFTY 50")
        _seed(store, prices=snapshot.prices_to_frame(_prices(periods=10), benchmark))

        _, loaded = snapshot.load_prices(["AAA"], period="1y", store=store, now=NOW)

        assert loaded is not None
        assert loaded.name == "NIFTY 50"
        np.testing.assert_allclose(loaded.to_numpy(), benchmark.to_numpy())

    def test_other_benchmarks_go_live(self, store, monkeypatch):
        _seed(store, prices=snapshot.prices_to_frame(_prices(), None))
        calls = []

        def fake_live(symbols, period="1y", benchmark=None):
            calls.append(benchmark)
            return pd.DataFrame(), None

        monkeypatch.setattr(snapshot, "fetch_price_history", fake_live)
        snapshot.load_prices(["AAA"], period="1y", benchmark="^BSESN", store=store, now=NOW)
        assert calls == ["^BSESN"]

    def test_unsupported_period_goes_live(self, store, monkeypatch):
        _seed(store, prices=snapshot.prices_to_frame(_prices(), None))
        calls = []
        monkeypatch.setattr(
            snapshot, "fetch_price_history",
            lambda symbols, period="1y", benchmark=None: (calls.append(period), (pd.DataFrame(), None))[1],
        )
        snapshot.load_prices(["AAA"], period="max", store=store, now=NOW)
        assert calls == ["max"]

    def test_stale_snapshot_goes_live(self, store, monkeypatch):
        _seed(
            store,
            generated_at=NOW - timedelta(days=3),
            prices=snapshot.prices_to_frame(_prices(), None),
        )
        calls = []

        def fake_live(symbols, period="1y", benchmark=None):
            calls.append(list(symbols))
            return pd.DataFrame(), None

        monkeypatch.setattr(snapshot, "fetch_price_history", fake_live)
        snapshot.load_prices(["AAA"], period="1y", store=store, now=NOW)
        assert calls == [["AAA"]]

    def test_no_store_goes_live(self, monkeypatch):
        calls = []

        def fake_live(symbols, period="1y", benchmark=None):
            calls.append(list(symbols))
            return pd.DataFrame(), None

        monkeypatch.setattr(snapshot, "fetch_price_history", fake_live)
        snapshot.load_prices(["AAA"], period="1y", store=None)
        assert calls == [["AAA"]]

    def test_a_broken_store_never_breaks_the_page(self, monkeypatch):
        class Broken:
            def read(self, name):
                raise RuntimeError("storage exploded")

        calls = []
        monkeypatch.setattr(
            snapshot, "fetch_price_history",
            lambda symbols, period="1y", benchmark=None: (calls.append(list(symbols)), (pd.DataFrame(), None))[1],
        )
        snapshot.load_prices(["AAA"], period="1y", store=Broken())
        assert calls == [["AAA"]]


class TestLoadCompanyData:
    FIELDS = {"trailingPE": "P/E (trailing)", "marketCap": "Market cap"}

    def _frame(self, symbols=("AAA",), labels=("P/E (trailing)", "Market cap")):
        return pd.DataFrame(
            {label: [float(i)] for i, label in enumerate(labels)},
            index=pd.Index(list(symbols), name="Symbol"),
        )

    def test_serves_from_the_snapshot(self, store, monkeypatch):
        _seed(store, company_data=self._frame())
        monkeypatch.setattr(snapshot, "fetch_company_data", _forbid_live())

        frame = snapshot.load_company_data(["AAA"], self.FIELDS, store=store, now=NOW)

        assert list(frame.columns) == list(self.FIELDS.values())
        assert list(frame.index) == ["AAA"]
        assert frame.index.name == "Symbol"

    def test_returns_only_the_requested_fields(self, store):
        _seed(store, company_data=self._frame(labels=("P/E (trailing)", "Market cap", "P/B")))
        frame = snapshot.load_company_data(
            ["AAA"], {"trailingPE": "P/E (trailing)"}, store=store, now=NOW
        )
        assert list(frame.columns) == ["P/E (trailing)"]

    def test_falls_back_when_a_requested_field_is_absent(self, store, monkeypatch):
        _seed(store, company_data=self._frame(labels=("P/E (trailing)",)))
        calls = []
        monkeypatch.setattr(
            snapshot, "fetch_company_data",
            lambda symbols, fields=None: (calls.append(list(symbols)), pd.DataFrame())[1],
        )
        snapshot.load_company_data(["AAA"], self.FIELDS, store=store, now=NOW)
        assert calls == [["AAA"]]

    def test_fetches_live_only_for_uncovered_symbols(self, store, monkeypatch):
        _seed(store, company_data=self._frame())
        calls = []

        def fake_live(symbols, fields=None):
            calls.append(list(symbols))
            return pd.DataFrame(
                {label: [9.0] for label in self.FIELDS.values()},
                index=pd.Index(["BBB"], name="Symbol"),
            )

        monkeypatch.setattr(snapshot, "fetch_company_data", fake_live)
        frame = snapshot.load_company_data(["AAA", "BBB"], self.FIELDS, store=store, now=NOW)

        assert calls == [["BBB"]]
        assert set(frame.index) == {"AAA", "BBB"}


class TestLoadDefaultRisk:
    def _frame(self, symbols=("AAA",)):
        return pd.DataFrame(
            {"Z-score": [2.5] * len(symbols), "Zone": ["Grey"] * len(symbols)},
            index=pd.Index(list(symbols), name="Symbol"),
        )

    def test_serves_from_the_snapshot(self, store, monkeypatch):
        _seed(store, default_risk=self._frame())
        monkeypatch.setattr(snapshot, "fetch_default_risk", _forbid_live())

        frame = snapshot.load_default_risk(["AAA"], store=store, now=NOW)

        assert frame.loc["AAA", "Zone"] == "Grey"

    def test_fetches_live_only_for_uncovered_symbols(self, store, monkeypatch):
        _seed(store, default_risk=self._frame())
        calls = []

        def fake_live(symbols, market_caps=None):
            calls.append(list(symbols))
            return pd.DataFrame(
                {"Z-score": [1.0], "Zone": ["Distress"]}, index=pd.Index(["BBB"], name="Symbol")
            )

        monkeypatch.setattr(snapshot, "fetch_default_risk", fake_live)
        frame = snapshot.load_default_risk(["AAA", "BBB"], store=store, now=NOW)

        assert calls == [["BBB"]]
        assert set(frame.index) == {"AAA", "BBB"}


class TestLoadEarnings:
    def _stored(self, symbol="AAA", when="2026-11-05"):
        return pd.DataFrame(
            [{"Symbol": symbol, "Date": when, "EPS estimate": 1.0, "Revenue estimate": 2.0}]
        )

    def test_recomputes_days_away_from_the_stored_date(self, store, monkeypatch):
        _seed(store, earnings=self._stored())
        monkeypatch.setattr(snapshot, "fetch_earnings_calendar", _forbid_live())

        frame = snapshot.load_earnings(["AAA"], store=store, now=NOW, today=TODAY)

        assert frame.loc[0, "Days away"] == 21
        assert list(frame.columns) == snapshot.EARNINGS_COLUMNS

    def test_past_dates_fall_back_to_a_live_fetch(self, store, monkeypatch):
        _seed(store, earnings=self._stored(when="2026-01-01"))
        calls = []
        monkeypatch.setattr(
            snapshot, "fetch_earnings_calendar",
            lambda symbols, today=None: (calls.append(list(symbols)), pd.DataFrame(
                columns=snapshot.EARNINGS_COLUMNS))[1],
        )
        snapshot.load_earnings(["AAA"], store=store, now=NOW, today=TODAY)
        assert calls == [["AAA"]]

    def test_empty_snapshot_falls_back(self, store, monkeypatch):
        calls = []
        monkeypatch.setattr(
            snapshot, "fetch_earnings_calendar",
            lambda symbols, today=None: (calls.append(list(symbols)), pd.DataFrame(
                columns=snapshot.EARNINGS_COLUMNS))[1],
        )
        snapshot.load_earnings(["AAA"], store=store, now=NOW, today=TODAY)
        assert calls == [["AAA"]]


class TestLoadSurveillance:
    def test_serves_from_the_snapshot(self, store, monkeypatch):
        frame = pd.DataFrame(
            [{"Symbol": "AAA", "Company": "Acme", "List": "GSM", "Stage": "Stage I",
              "Code": "1", "Updated": "15-Oct-2026"}]
        )
        _seed(store, surveillance=frame)
        monkeypatch.setattr(snapshot, "fetch_surveillance", _forbid_live())

        loaded = snapshot.load_surveillance(store=store, now=NOW)

        assert list(loaded.columns) == snapshot.SURVEILLANCE_COLUMNS
        assert loaded.loc[0, "Symbol"] == "AAA"

    def test_falls_back_when_the_dataset_is_absent(self, store, monkeypatch):
        _seed(store, prices=snapshot.prices_to_frame(_prices(periods=3), None))
        calls = []
        monkeypatch.setattr(
            snapshot, "fetch_surveillance",
            lambda: (calls.append(1), pd.DataFrame(columns=snapshot.SURVEILLANCE_COLUMNS))[1],
        )
        snapshot.load_surveillance(store=store, now=NOW)
        assert calls == [1]


class TestFetchUniverseData:
    def test_records_failures_and_keeps_the_rest(self, monkeypatch):
        monkeypatch.setattr(
            snapshot, "fetch_price_history",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("yahoo down")),
        )
        monkeypatch.setattr(
            snapshot, "fetch_company_data",
            lambda symbols, fields=None: pd.DataFrame(
                {"Market cap": [1.0]}, index=pd.Index(["AAA"], name="Symbol")
            ),
        )
        monkeypatch.setattr(snapshot, "fetch_default_risk", lambda symbols, caps=None: pd.DataFrame(
            index=pd.Index([], name="Symbol")))
        monkeypatch.setattr(snapshot, "fetch_earnings_calendar",
                            lambda symbols, today=None: pd.DataFrame(columns=snapshot.EARNINGS_COLUMNS))
        monkeypatch.setattr(snapshot, "fetch_surveillance",
                            lambda: pd.DataFrame(columns=snapshot.SURVEILLANCE_COLUMNS))

        frames, failures = snapshot.fetch_universe_data(["AAA"])

        assert "prices" not in frames
        assert failures["prices"] == ["RuntimeError: yahoo down"]
        assert set(frames) == {"company_data", "default_risk", "earnings", "surveillance"}
        assert list(frames["company_data"].columns) == ["Symbol", "Market cap"]


# --------------------------------------------------------------------------- #
# App integration
# --------------------------------------------------------------------------- #
class TestCoPilotIntegration:
    """The Co-Pilot must serve its default view from the snapshot alone."""

    def test_correlation_renders_with_the_provider_dead(self, tmp_path, monkeypatch):
        symbols = snapshot.symbols_from_holdings(
            REPO_ROOT / "data" / "holdings-sample.xlsx"
        )
        assert symbols, "the sample portfolio should define a universe"

        index = pd.date_range("2025-01-01", periods=300, freq="B", name="Date")
        rng = np.random.default_rng(3)
        prices = pd.DataFrame(
            {name: 100 + rng.normal(0, 1, 300).cumsum() for name in symbols},
            index=index,
        )
        benchmark = pd.Series(
            1000 + rng.normal(0, 1, 300).cumsum(), index=index, name="NIFTY 50"
        )

        store = snapshot.LocalStore(tmp_path / "snapshots")
        snapshot.write_snapshot(
            store,
            {"prices": snapshot.prices_to_frame(prices, benchmark)},
            generated_at=datetime.now(timezone.utc),
            universe=symbols,
        )
        monkeypatch.setenv("SNAPSHOT_DIR", str(store.root))

        # Any live fetch is a test failure: the snapshot must cover everything
        # the default (Correlation) view needs.
        provider = types.ModuleType("yfinance")

        def _dead(*args, **kwargs):
            raise AssertionError("the live provider must not be called")

        provider.download = _dead
        provider.Ticker = _dead
        monkeypatch.setitem(sys.modules, "yfinance", provider)

        app = AppTest.from_file(str(CO_PILOT), default_timeout=60)
        app.run()

        assert not app.exception
        assert len(app.get("plotly_chart")) >= 1, "correlation heatmap should render"
