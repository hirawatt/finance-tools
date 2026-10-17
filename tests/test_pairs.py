"""Tests for utils.pairs (pure candidate selection and spread statistics)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils.pairs import (
    PAIR_COLUMNS,
    candidate_pairs,
    hedge_ratio,
    rank_pairs,
    spread_zscore,
)

DATES = pd.date_range("2026-01-01", periods=120, freq="B", name="Date")
TIME = np.arange(len(DATES))


def _prices():
    """A and B share daily returns (A stretched at the end); C is noise."""
    rng = np.random.default_rng(1)
    common = rng.normal(0, 0.01, len(TIME))
    a_returns = common + rng.normal(0, 0.002, len(TIME))
    b_returns = common + rng.normal(0, 0.002, len(TIME))
    a = 100 * np.cumprod(1 + a_returns)
    b = 100 * np.cumprod(1 + b_returns)
    a[-1] *= 1.06  # stretch the pair on the last session
    c = 100 * np.cumprod(1 + rng.normal(0, 0.015, len(TIME)))
    return pd.DataFrame({"A": a, "B": b, "C": c}, index=DATES)


class TestCandidatePairs:
    def test_pairs_within_an_industry(self):
        sectors = pd.DataFrame(
            {
                "NSE code": ["AAA", "BBB", "CCC", "DDD"],
                "Industry": ["Cement", "Cement", "IT", "IT"],
            }
        )
        assert set(candidate_pairs(sectors)) == {
            ("AAA", "BBB", "Cement"),
            ("CCC", "DDD", "IT"),
        }

    def test_reads_a_renamed_symbol_column(self):
        sectors = pd.DataFrame({"Symbol": ["AAA", "BBB"], "Industry": ["Cement", "Cement"]})
        assert candidate_pairs(sectors) == [("AAA", "BBB", "Cement")]

    def test_limits_to_the_given_universe(self):
        sectors = pd.DataFrame(
            {"NSE code": ["AAA", "BBB", "CCC"], "Industry": ["Cement"] * 3}
        )
        assert candidate_pairs(sectors, symbols=["aaa", "bbb"]) == [("AAA", "BBB", "Cement")]

    def test_degenerate_inputs(self):
        assert candidate_pairs(None) == []
        assert candidate_pairs(pd.DataFrame()) == []
        assert candidate_pairs(pd.DataFrame({"NSE code": ["AAA"]})) == []


class TestHedgeRatio:
    def test_recovers_the_log_log_slope(self):
        prices = pd.DataFrame(
            {"A": np.exp(0.02 * TIME), "B": np.exp(0.01 * TIME)}, index=DATES
        )
        assert round(hedge_ratio(prices, "A", "B"), 6) == 2.0

    def test_missing_columns_are_nan(self):
        assert np.isnan(hedge_ratio(pd.DataFrame({"A": [1.0]}), "A", "MISSING"))


class TestSpreadZScore:
    def test_flags_the_stretched_side(self):
        stats = spread_zscore(_prices(), "A", "B", lookback=60)
        assert stats["Spread z"] > 2
        assert stats["Signal"] == "A rich vs B"
        assert stats["Correlation"] > 0.8

    def test_short_history_is_not_scored(self):
        short = pd.DataFrame({"A": [1.0, 2.0, 3.0], "B": [1.0, 2.0, 3.0]})
        assert spread_zscore(short, "A", "B") is None

    def test_missing_column_is_not_scored(self):
        assert spread_zscore(_prices(), "A", "MISSING") is None


class TestRankPairs:
    def test_keeps_the_stretched_correlated_pair_only(self):
        result = rank_pairs(
            _prices(),
            [("A", "B", "Trend"), ("A", "C", "Noise")],
            lookback=60,
            threshold=2.0,
            min_correlation=0.5,
        )
        assert list(result.columns) == PAIR_COLUMNS
        assert set(zip(result["Symbol A"], result["Symbol B"])) == {("A", "B")}

    def test_threshold_can_exclude_everything(self):
        result = rank_pairs(_prices(), [("A", "B", "Trend")], threshold=50.0)
        assert result.empty
        assert list(result.columns) == PAIR_COLUMNS

    def test_empty_input(self):
        assert rank_pairs(_prices(), []).empty
