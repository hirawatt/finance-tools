"""Tests for utils.default_risk (pure extraction and scoring, no network)."""

import unittest

import pandas as pd

from utils.default_risk import (
    altman_z_score,
    classify_z,
    extract_z_inputs,
    fetch_default_risk,
)


def _balance_sheet(with_working_capital: bool = False) -> pd.DataFrame:
    items = {
        "Total Assets": 1000.0,
        "Current Assets": 100.0,
        "Current Liabilities": 400.0,
        "Retained Earnings": 200.0,
        "Total Liabilities Net Minority Interest": 400.0,
    }
    if with_working_capital:
        items["Working Capital"] = -300.0
    return pd.DataFrame({"2024-03-31": items})


def _income_stmt() -> pd.DataFrame:
    return pd.DataFrame({"2024-03-31": {"EBIT": 150.0, "Total Revenue": 800.0}})


class TestExtractZInputs(unittest.TestCase):
    def test_extracts_items(self):
        inputs = extract_z_inputs(_balance_sheet(), _income_stmt())
        self.assertEqual(inputs["total_assets"], 1000.0)
        self.assertEqual(inputs["retained_earnings"], 200.0)
        self.assertEqual(inputs["total_liabilities"], 400.0)
        self.assertEqual(inputs["ebit"], 150.0)
        self.assertEqual(inputs["revenue"], 800.0)

    def test_working_capital_fallback(self):
        inputs = extract_z_inputs(_balance_sheet(), _income_stmt())
        self.assertEqual(inputs["working_capital"], -300.0)  # 100 - 400

    def test_prefers_reported_working_capital(self):
        inputs = extract_z_inputs(_balance_sheet(with_working_capital=True), _income_stmt())
        self.assertEqual(inputs["working_capital"], -300.0)

    def test_missing_frames(self):
        inputs = extract_z_inputs(None, None)
        self.assertTrue(all(value is None for value in inputs.values()))

    def test_picks_most_recent_non_null(self):
        bs = pd.DataFrame(
            {
                "2023-03-31": {"Total Assets": 900.0},
                "2024-03-31": {"Total Assets": 1000.0},
            }
        )
        self.assertEqual(extract_z_inputs(bs, None)["total_assets"], 1000.0)


class TestAltmanZScore(unittest.TestCase):
    def _inputs(self):
        return {
            "total_assets": 1000.0,
            "working_capital": 100.0,
            "retained_earnings": 200.0,
            "ebit": 150.0,
            "total_liabilities": 400.0,
            "revenue": 800.0,
        }

    def test_known_value(self):
        # 1.2*0.1 + 1.4*0.2 + 3.3*0.15 + 0.6*1.5 + 1.0*0.8 = 2.595
        self.assertAlmostEqual(altman_z_score(self._inputs(), 600.0), 2.595, places=6)

    def test_missing_market_cap(self):
        self.assertIsNone(altman_z_score(self._inputs(), None))

    def test_missing_component(self):
        inputs = self._inputs()
        inputs["ebit"] = None
        self.assertIsNone(altman_z_score(inputs, 600.0))

    def test_non_positive_assets(self):
        inputs = self._inputs()
        inputs["total_assets"] = 0.0
        self.assertIsNone(altman_z_score(inputs, 600.0))


class TestClassifyZ(unittest.TestCase):
    def test_zone_boundaries(self):
        self.assertEqual(classify_z(3.5), "Safe")
        self.assertEqual(classify_z(2.99), "Safe")
        self.assertEqual(classify_z(2.5), "Grey")
        self.assertEqual(classify_z(1.81), "Grey")
        self.assertEqual(classify_z(1.0), "Distress")
        self.assertIsNone(classify_z(None))


class TestFetchDefaultRisk(unittest.TestCase):
    def test_empty_symbols(self):
        frame = fetch_default_risk([])
        self.assertTrue(frame.empty)
        self.assertEqual(frame.index.name, "Symbol")


if __name__ == "__main__":
    unittest.main()
