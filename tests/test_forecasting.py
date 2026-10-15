"""Tests for utils.forecasting (deterministic Monte Carlo projections)."""

import unittest

import numpy as np
import pandas as pd

from utils.forecasting import forecast_paths


def _returns(periods: int = 250, seed: int = 11) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=periods, freq="B")
    return pd.Series(rng.normal(0.0004, 0.012, periods), index=idx)


class TestForecastPaths(unittest.TestCase):
    def test_shape_and_columns(self):
        frame = forecast_paths(_returns(), 100.0, horizon=21, simulations=500, seed=1)
        # horizon steps plus the starting point at step 0.
        self.assertEqual(len(frame), 22)
        self.assertEqual(frame.index[0], 0)
        self.assertEqual(list(frame.columns), ["P5", "P25", "P50", "P75", "P95"])

    def test_step_zero_is_start_value(self):
        frame = forecast_paths(_returns(), 100.0, horizon=10, simulations=200, seed=1)
        self.assertTrue(np.allclose(frame.loc[0], 100.0))

    def test_quantiles_are_ordered(self):
        frame = forecast_paths(_returns(), 100.0, horizon=30, simulations=800, seed=2)
        ordered = frame[["P5", "P25", "P50", "P75", "P95"]].to_numpy()
        self.assertTrue((np.diff(ordered, axis=1) >= 0).all())

    def test_deterministic_for_seed(self):
        first = forecast_paths(_returns(), 100.0, horizon=15, simulations=300, seed=7)
        second = forecast_paths(_returns(), 100.0, horizon=15, simulations=300, seed=7)
        pd.testing.assert_frame_equal(first, second)

    def test_zero_volatility_stays_flat(self):
        flat = pd.Series(np.zeros(60))
        frame = forecast_paths(flat, 250.0, horizon=5, simulations=100, seed=0)
        self.assertTrue(np.allclose(frame.to_numpy(), 250.0))

    def test_insufficient_input_is_empty(self):
        self.assertTrue(forecast_paths(pd.Series([0.01]), 100.0).empty)
        self.assertTrue(forecast_paths(pd.Series(dtype=float), 100.0).empty)

    def test_invalid_horizon_is_empty(self):
        self.assertTrue(forecast_paths(_returns(), 100.0, horizon=0).empty)


if __name__ == "__main__":
    unittest.main()
