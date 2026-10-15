"""Tests for utils.earnings (pure calendar parsing, no network)."""

import unittest
from datetime import date

import pandas as pd

from utils.earnings import EARNINGS_COLUMNS, parse_next_earnings, upcoming

TODAY = date(2026, 10, 15)


class TestParseNextEarnings(unittest.TestCase):
    def test_picks_earliest_future_date(self):
        calendar = {
            "Earnings Date": [date(2026, 10, 10), date(2026, 11, 5), date(2026, 10, 20)],
            "Earnings Average": 12.5,
            "Revenue Average": 1e10,
        }
        parsed = parse_next_earnings("ACME", calendar, TODAY)
        self.assertEqual(parsed["Date"], date(2026, 10, 20))
        self.assertEqual(parsed["Days away"], 5)
        self.assertEqual(parsed["EPS estimate"], 12.5)

    def test_today_counts_as_upcoming(self):
        parsed = parse_next_earnings("ACME", {"Earnings Date": [TODAY]}, TODAY)
        self.assertEqual(parsed["Days away"], 0)

    def test_ignores_all_past_dates(self):
        parsed = parse_next_earnings("ACME", {"Earnings Date": [date(2026, 1, 1)]}, TODAY)
        self.assertIsNone(parsed)

    def test_empty_or_missing(self):
        self.assertIsNone(parse_next_earnings("ACME", {"Earnings Date": []}, TODAY))
        self.assertIsNone(parse_next_earnings("ACME", {}, TODAY))
        self.assertIsNone(parse_next_earnings("ACME", None, TODAY))

    def test_accepts_single_value_and_iso_string(self):
        parsed = parse_next_earnings("ACME", {"Earnings Date": "2026-12-01"}, TODAY)
        self.assertEqual(parsed["Date"], date(2026, 12, 1))


class TestUpcoming(unittest.TestCase):
    def test_filters_by_horizon_and_sorts(self):
        frame = pd.DataFrame(
            [
                {"Symbol": "A", "Date": date(2026, 12, 1), "Days away": 47,
                 "EPS estimate": None, "Revenue estimate": None},
                {"Symbol": "B", "Date": date(2026, 10, 20), "Days away": 5,
                 "EPS estimate": None, "Revenue estimate": None},
                {"Symbol": "C", "Date": date(2027, 3, 1), "Days away": 137,
                 "EPS estimate": None, "Revenue estimate": None},
            ],
            columns=EARNINGS_COLUMNS,
        )
        result = upcoming(frame, within_days=90)
        self.assertEqual(result["Symbol"].tolist(), ["B", "A"])

    def test_empty(self):
        for empty in (None, pd.DataFrame()):
            self.assertTrue(upcoming(empty).empty)


if __name__ == "__main__":
    unittest.main()
