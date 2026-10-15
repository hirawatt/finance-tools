"""Tests for utils.red_flags (pure rule engine, no network)."""

import unittest

import numpy as np
import pandas as pd

from utils.market_data import FUNDAMENTAL_FIELDS, RISK_FIELDS
from utils.red_flags import FLAG_COLUMNS, detect_red_flags, flag_summary

PE = FUNDAMENTAL_FIELDS["trailingPE"]
PB = FUNDAMENTAL_FIELDS["priceToBook"]
DEBT = RISK_FIELDS["debtToEquity"]
CURRENT_RATIO = RISK_FIELDS["currentRatio"]
PROFIT_MARGIN = RISK_FIELDS["profitMargins"]
OPERATING_MARGIN = RISK_FIELDS["operatingMargins"]
REVENUE_GROWTH = RISK_FIELDS["revenueGrowth"]
EARNINGS_GROWTH = RISK_FIELDS["earningsGrowth"]
FREE_CASH_FLOW = RISK_FIELDS["freeCashflow"]
NET_INCOME = RISK_FIELDS["netIncomeToCommon"]

COLUMNS = [PE, PB, DEBT, CURRENT_RATIO, PROFIT_MARGIN, OPERATING_MARGIN,
           REVENUE_GROWTH, EARNINGS_GROWTH, FREE_CASH_FLOW, NET_INCOME]

CLEAN = {
    PE: 20.0, PB: 3.0, DEBT: 50.0, CURRENT_RATIO: 1.5, PROFIT_MARGIN: 0.10,
    OPERATING_MARGIN: 0.12, REVENUE_GROWTH: 0.10, EARNINGS_GROWTH: 0.10,
    FREE_CASH_FLOW: 1e9, NET_INCOME: 1e9,
}


def frame(rows: dict) -> pd.DataFrame:
    """Build a company-data frame from {symbol: {override: value}}."""
    data = {}
    for symbol, overrides in rows.items():
        row = dict(CLEAN)
        row.update(overrides)
        data[symbol] = row
    result = pd.DataFrame.from_dict(data, orient="index", columns=COLUMNS)
    result.index.name = "Symbol"
    return result


def flags_for(**overrides):
    result = detect_red_flags(frame({"X": overrides}))
    return set(result["Flag"]) if not result.empty else set()


class TestRuleDetection(unittest.TestCase):
    def test_clean_holding_has_no_flags(self):
        self.assertEqual(flags_for(), set())

    def test_all_missing_data_has_no_flags(self):
        empty = frame({"X": {c: np.nan for c in COLUMNS}})
        self.assertTrue(detect_red_flags(empty).empty)

    def test_loss_making_via_net_income(self):
        self.assertIn("Loss-making", flags_for(**{NET_INCOME: -5e9}))

    def test_loss_making_via_negative_pe(self):
        self.assertIn("Loss-making", flags_for(**{PE: -3.0}))

    def test_loss_making_via_margin(self):
        self.assertIn("Loss-making", flags_for(**{PROFIT_MARGIN: -0.02}))

    def test_high_leverage(self):
        self.assertIn("High leverage", flags_for(**{DEBT: 646.0}))

    def test_elevated_leverage_band(self):
        flagged = flags_for(**{DEBT: 150.0})
        self.assertIn("Elevated leverage", flagged)
        self.assertNotIn("High leverage", flagged)

    def test_moderate_leverage_is_clean(self):
        self.assertEqual(flags_for(**{DEBT: 90.0}), set())

    def test_negative_book_value(self):
        self.assertIn("Negative book value", flags_for(**{PB: -0.19}))

    def test_negative_free_cash_flow(self):
        self.assertIn("Negative free cash flow", flags_for(**{FREE_CASH_FLOW: -1e9}))

    def test_falling_revenue_and_earnings(self):
        flagged = flags_for(**{REVENUE_GROWTH: -0.05, EARNINGS_GROWTH: -0.22})
        self.assertIn("Falling revenue", flagged)
        self.assertIn("Falling earnings", flagged)

    def test_weak_liquidity(self):
        self.assertIn("Weak liquidity", flags_for(**{CURRENT_RATIO: 0.8}))

    def test_operating_losses(self):
        self.assertIn("Operating losses", flags_for(**{OPERATING_MARGIN: -0.3}))

    def test_stretched_valuation(self):
        self.assertIn("Stretched valuation", flags_for(**{PE: 63.5}))


class TestDetectRedFlags(unittest.TestCase):
    def test_empty_input(self):
        result = detect_red_flags(pd.DataFrame())
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), FLAG_COLUMNS)

    def test_sorted_by_severity(self):
        data = frame(
            {
                "LOW": {PE: 80.0},
                "HIGH": {DEBT: 500.0},
                "MED": {EARNINGS_GROWTH: -0.1},
            }
        )
        severities = detect_red_flags(data)["Severity"].tolist()
        self.assertEqual(severities, ["high", "medium", "low"])


class TestFlagSummary(unittest.TestCase):
    def test_worst_severity_and_count(self):
        data = frame(
            {
                "BADC": {DEBT: 500.0, EARNINGS_GROWTH: -0.1, REVENUE_GROWTH: -0.1},
                "MILD": {PE: 80.0},
            }
        )
        summary = flag_summary(detect_red_flags(data))

        self.assertEqual(summary.loc["BADC", "Worst severity"], "high")
        self.assertEqual(summary.loc["BADC", "Flags"], 3)
        self.assertIn("High leverage", summary.loc["BADC", "Details"])
        self.assertEqual(summary.loc["MILD", "Worst severity"], "low")
        # Highest severity first.
        self.assertEqual(summary.index[0], "BADC")

    def test_empty(self):
        self.assertTrue(flag_summary(pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()
