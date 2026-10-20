"""Tests for utils.market_data analytics helpers.

These use real pandas/numpy objects (no module mocking) so the functions are
exercised as they run in the app.
"""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from utils.market_data import (
    MIN_OBSERVATIONS,
    compute_beta,
    compute_returns,
    correlation_matrix,
    fetch_fundamentals,
    fetch_price_history,
    full_metrics_report,
    performance_summary,
    to_ticker,
    weighted_average_pe,
    weighted_portfolio_returns,
)


def _sample_returns(periods: int = 60, seed: int = 7) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=periods, freq="B")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "AAA": rng.normal(0.0005, 0.010, periods),
            "BBB": rng.normal(0.0004, 0.014, periods),
        },
        index=idx,
    )


class TestToTicker(unittest.TestCase):
    def test_appends_nse_suffix(self):
        self.assertEqual(to_ticker("polycab"), "POLYCAB.NS")

    def test_index_passthrough(self):
        self.assertEqual(to_ticker("^NSEI"), "^NSEI")

    def test_already_qualified_passthrough(self):
        self.assertEqual(to_ticker("TCS.NS"), "TCS.NS")

    def test_renamed_ticker_is_resolved(self):
        self.assertEqual(to_ticker("zomato"), "ETERNAL.NS")
        self.assertEqual(to_ticker("BAJAJAUTO"), "BAJAJ-AUTO.NS")
        self.assertEqual(to_ticker("MCDOWELL_N"), "UNITDSPR.NS")

    def test_bse_only_ticker_keeps_its_exchange(self):
        self.assertEqual(to_ticker("PANAENERG"), "PANAENERG.BO")
        self.assertEqual(to_ticker("RASIELEC-X"), "RASIELEC.BO")


class TestAliasedDownloads(unittest.TestCase):
    """A renamed ticker comes back under the code the caller asked for."""

    def _download(self, ticker, periods=3):
        index = pd.date_range("2026-01-01", periods=periods, freq="B", name="Date")
        data = pd.DataFrame(
            {
                ("Close", ticker): [10.0, 11.0, 12.0][:periods],
                ("Volume", ticker): [100.0, 200.0, 300.0][:periods],
            },
            index=index,
        )
        data.columns = pd.MultiIndex.from_tuples(data.columns)
        return data

    def test_renamed_symbol_is_returned_under_the_requested_code(self):
        with patch("utils.market_data._download", return_value=self._download("ETERNAL.NS")):
            prices, benchmark = fetch_price_history(["ZOMATO"], benchmark=None)

        self.assertEqual(list(prices.columns), ["ZOMATO"])
        self.assertIsNone(benchmark)

    def test_two_codes_for_one_ticker_both_appear(self):
        with patch("utils.market_data._download", return_value=self._download("ORISSAMINE.NS")):
            prices, _ = fetch_price_history(["ORISSAMINE6", "ORISSAMINE"], benchmark=None)

        self.assertEqual(list(prices.columns), ["ORISSAMINE6", "ORISSAMINE"])


class TestComputeReturns(unittest.TestCase):
    def test_first_row_dropped_and_values_correct(self):
        prices = pd.DataFrame(
            {"X": [100.0, 110.0, 121.0]},
            index=pd.date_range("2024-01-01", periods=3, freq="B"),
        )
        returns = compute_returns(prices)

        self.assertEqual(len(returns), 2)
        self.assertAlmostEqual(returns["X"].iloc[0], 0.10, places=6)
        self.assertAlmostEqual(returns["X"].iloc[1], 0.10, places=6)

    def test_empty_input(self):
        self.assertTrue(compute_returns(pd.DataFrame()).empty)


class TestCorrelationMatrix(unittest.TestCase):
    def test_shape_diagonal_and_symmetry(self):
        corr = correlation_matrix(_sample_returns())

        self.assertEqual(corr.shape, (2, 2))
        np.testing.assert_allclose(np.diag(corr), [1.0, 1.0])
        self.assertAlmostEqual(corr.iloc[0, 1], corr.iloc[1, 0], places=12)
        self.assertTrue((-1.0 <= corr.to_numpy()).all() and (corr.to_numpy() <= 1.0).all())


class TestComputeBeta(unittest.TestCase):
    def test_recovers_known_beta(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="B")
        rng = np.random.default_rng(0)
        benchmark = pd.Series(rng.normal(0.0005, 0.01, 100), index=idx, name="NIFTY 50")
        returns = pd.DataFrame({"DOUBLE": 2 * benchmark}, index=idx)

        beta = compute_beta(returns, benchmark)

        self.assertAlmostEqual(beta["DOUBLE"], 2.0, places=6)

    def test_skips_when_insufficient_overlap(self):
        idx = pd.date_range("2024-01-01", periods=5, freq="B")
        benchmark = pd.Series(np.linspace(-0.01, 0.01, 5), index=idx)
        returns = pd.DataFrame({"X": np.linspace(-0.02, 0.02, 5)}, index=idx)

        self.assertTrue(compute_beta(returns, benchmark).empty)

    def test_empty_inputs(self):
        self.assertTrue(compute_beta(pd.DataFrame(), pd.Series(dtype=float)).empty)


class TestWeightedPortfolioReturns(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range("2024-01-01", periods=4, freq="B")
        self.returns = pd.DataFrame(
            {"A": [0.01, 0.02, -0.01, 0.0], "B": [0.02, -0.01, 0.03, 0.01]},
            index=idx,
        )

    def test_normalises_weights(self):
        weights = pd.Series({"A": 60.0, "B": 40.0})
        result = weighted_portfolio_returns(self.returns, weights)
        expected = self.returns["A"] * 0.6 + self.returns["B"] * 0.4
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_renormalises_over_available_columns(self):
        # "C" is weighted but has no return data, so A/B are renormalised 60/40.
        weights = pd.Series({"A": 60.0, "B": 40.0, "C": 100.0})
        result = weighted_portfolio_returns(self.returns, weights)
        expected = self.returns["A"] * 0.6 + self.returns["B"] * 0.4
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_zero_total_weight_returns_empty(self):
        self.assertTrue(weighted_portfolio_returns(self.returns, pd.Series({"A": 0.0})).empty)


class TestPerformanceSummary(unittest.TestCase):
    def test_labels_present(self):
        summary = performance_summary(_sample_returns()["AAA"])
        expected = {
            "Cumulative Return",
            "CAGR",
            "Volatility (ann.)",
            "Sharpe",
            "Sortino",
            "Calmar",
            "Max Drawdown",
            "Value at Risk (95%)",
        }
        self.assertEqual(set(summary.index), expected)
        self.assertFalse(summary.isna().all())

    def test_tiny_series_is_nan(self):
        summary = performance_summary(pd.Series([0.01]))
        self.assertTrue(summary.isna().all())

    def test_full_metrics_report(self):
        report = full_metrics_report(_sample_returns()["AAA"])
        self.assertFalse(report.empty)
        self.assertIn("Sharpe", report.index)


class TestWeightedAveragePE(unittest.TestCase):
    def test_uses_harmonic_mean_not_arithmetic(self):
        # Equal weights: 1 / (0.5/10 + 0.5/20) = 13.33... (not the 15 arithmetic mean)
        pe = pd.Series({"A": 10.0, "B": 20.0})
        weights = pd.Series({"A": 1.0, "B": 1.0})
        self.assertAlmostEqual(weighted_average_pe(pe, weights), 13.333333, places=4)

    def test_respects_value_weights(self):
        pe = pd.Series({"A": 10.0, "B": 20.0})
        weights = pd.Series({"A": 3.0, "B": 1.0})
        self.assertAlmostEqual(weighted_average_pe(pe, weights), 11.428571, places=4)

    def test_excludes_non_positive_pe(self):
        pe = pd.Series({"A": 10.0, "B": -5.0, "C": 20.0})
        weights = pd.Series({"A": 1.0, "B": 1.0, "C": 1.0})
        self.assertAlmostEqual(weighted_average_pe(pe, weights), 13.333333, places=4)

    def test_returns_none_without_usable_data(self):
        self.assertIsNone(weighted_average_pe(pd.Series(dtype=float), pd.Series(dtype=float)))
        self.assertIsNone(
            weighted_average_pe(pd.Series({"A": -3.0}), pd.Series({"A": 1.0}))
        )


class TestFetchFundamentals(unittest.TestCase):
    def test_empty_symbols(self):
        frame = fetch_fundamentals([])
        self.assertTrue(frame.empty)
        self.assertEqual(frame.index.name, "Symbol")


class TestFetchPriceHistory(unittest.TestCase):
    def test_no_symbols_no_benchmark(self):
        prices, benchmark = fetch_price_history([], benchmark=None)
        self.assertTrue(prices.empty)
        self.assertIsNone(benchmark)


if __name__ == "__main__":
    unittest.main()
