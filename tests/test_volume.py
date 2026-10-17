"""Tests for utils.volume (pure volume-anomaly detection)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils.volume import VOLUME_COLUMNS, volume_anomalies

DATES = pd.date_range("2026-01-01", periods=21, freq="B", name="Date")


def _volumes():
    return pd.DataFrame(
        {
            "AAA": [100.0] * 20 + [400.0],
            "BBB": [100.0] * 21,
            "SPIKE": [100.0] * 20 + [500.0],
        },
        index=DATES,
    )


def _closes():
    closes = pd.DataFrame(
        {"AAA": [100.0] * 20 + [110.0], "BBB": [50.0] * 21, "SPIKE": [10.0] * 21},
        index=DATES,
    )
    return closes


class TestVolumeAnomalies:
    def test_flags_only_the_spiking_symbols(self):
        found = volume_anomalies(_volumes(), min_turnover=0)
        assert set(found["Symbol"]) == {"AAA", "SPIKE"}

    def test_baseline_excludes_the_latest_session(self):
        found = volume_anomalies(_volumes(), min_turnover=0).set_index("Symbol")
        assert found.loc["AAA", "Ratio"] == 4.0  # 400 / 100, not 400 / 114

    def test_orders_by_ratio_descending(self):
        found = volume_anomalies(_volumes(), min_turnover=0)
        assert found["Symbol"].tolist() == ["SPIKE", "AAA"]
        assert found["Ratio"].is_monotonic_decreasing

    def test_threshold_is_respected(self):
        assert volume_anomalies(_volumes(), threshold=6.0, min_turnover=0).empty

    def test_empty_and_single_row_inputs(self):
        assert volume_anomalies(None).empty
        assert volume_anomalies(pd.DataFrame()).empty
        assert volume_anomalies(_volumes().iloc[:1]).empty

    def test_columns(self):
        found = volume_anomalies(_volumes(), min_turnover=0)
        assert list(found.columns) == VOLUME_COLUMNS

    def test_return_and_turnover_come_from_closes(self):
        found = volume_anomalies(_volumes(), _closes(), min_turnover=0).set_index("Symbol")
        assert round(found.loc["AAA", "Return"], 6) == 0.1
        assert found.loc["AAA", "Turnover"] == 400 * 110

    def test_min_turnover_drops_tiny_names(self):
        # SPIKE trades a lot of a cheap stock: 500 x 10 = 5,000 rupees.
        found = volume_anomalies(_volumes(), _closes(), min_turnover=1e4)
        assert set(found["Symbol"]) == {"AAA"}  # 400 x 110 = 44,000

    def test_missing_closes_leave_return_blank(self):
        found = volume_anomalies(_volumes(), min_turnover=0)
        assert found["Return"].isna().all()
        assert found["Turnover"].isna().all()
