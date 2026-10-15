"""Tests for utils.rebalancing (all pure, no network)."""

import unittest

import numpy as np
import pandas as pd

from utils.rebalancing import (
    apply_weight_cap,
    equal_weights,
    inverse_volatility_weights,
    rebalancing_plan,
    risk_parity_weights,
    target_weights,
    turnover,
)


def _sample_returns(periods: int = 300, seed: int = 3) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=periods, freq="B")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "A": rng.normal(0, 0.008, periods),
            "B": rng.normal(0, 0.020, periods),
            "C": rng.normal(0, 0.035, periods),
        },
        index=idx,
    )


class TestEqualWeights(unittest.TestCase):
    def test_sums_to_one_and_is_uniform(self):
        weights = equal_weights(["A", "B", "C"])
        self.assertAlmostEqual(weights.sum(), 1.0)
        self.assertTrue(np.allclose(weights, 1 / 3))

    def test_empty(self):
        self.assertTrue(equal_weights([]).empty)


class TestInverseVolatilityWeights(unittest.TestCase):
    def test_lower_vol_gets_more_weight(self):
        weights = inverse_volatility_weights(_sample_returns())
        self.assertAlmostEqual(weights.sum(), 1.0)
        self.assertGreater(weights["A"], weights["B"])
        self.assertGreater(weights["B"], weights["C"])

    def test_empty(self):
        self.assertTrue(inverse_volatility_weights(pd.DataFrame()).empty)


class TestRiskParityWeights(unittest.TestCase):
    def _risk_contributions(self, weights, returns):
        cov = returns.cov().to_numpy()
        w = weights.to_numpy()
        return w * (cov @ w) / np.sqrt(w @ cov @ w)

    def test_contributions_are_equalised(self):
        returns = _sample_returns()
        weights = risk_parity_weights(returns)
        self.assertAlmostEqual(weights.sum(), 1.0)
        contributions = self._risk_contributions(weights, returns)
        self.assertLess(contributions.max() - contributions.min(), 1e-5)

    def test_single_asset(self):
        returns = pd.DataFrame({"A": np.linspace(-0.01, 0.01, 50)})
        weights = risk_parity_weights(returns)
        self.assertAlmostEqual(weights["A"], 1.0)

    def test_empty(self):
        self.assertTrue(risk_parity_weights(pd.DataFrame()).empty)


class TestApplyWeightCap(unittest.TestCase):
    def test_caps_and_renormalises(self):
        capped = apply_weight_cap(pd.Series({"A": 0.7, "B": 0.15, "C": 0.15}), 0.5)
        self.assertAlmostEqual(capped.sum(), 1.0)
        self.assertLessEqual(capped.max(), 0.5 + 1e-9)
        self.assertAlmostEqual(capped["A"], 0.5)

    def test_infeasible_cap_falls_back_to_equal(self):
        capped = apply_weight_cap(equal_weights(["S0", "S1", "S2"]), 0.05)
        self.assertTrue(np.allclose(capped, 1 / 3))

    def test_empty(self):
        self.assertTrue(apply_weight_cap(pd.Series(dtype=float), 0.3).empty)


class TestTargetWeights(unittest.TestCase):
    def test_dispatch_and_normalisation(self):
        returns = _sample_returns()
        for strategy in ("Equal weight", "Inverse volatility", "Risk parity"):
            weights = target_weights(returns, strategy)
            self.assertAlmostEqual(weights.sum(), 1.0, msg=strategy)

    def test_applies_cap(self):
        # Inverse-vol gives A ~0.61; a 0.5 cap is feasible for 3 assets and binds.
        weights = target_weights(_sample_returns(), "Inverse volatility", max_weight=0.50)
        self.assertAlmostEqual(weights.sum(), 1.0)
        self.assertLessEqual(weights.max(), 0.50 + 1e-9)

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            target_weights(_sample_returns(), "moon math")


class TestRebalancingPlan(unittest.TestCase):
    def test_trades_sized_correctly(self):
        current_values = pd.Series({"A": 100.0, "B": 300.0})
        current_quantities = pd.Series({"A": 10.0, "B": 15.0})
        latest_prices = pd.Series({"A": 10.0, "B": 20.0})
        target = pd.Series({"A": 0.5, "B": 0.5})

        plan = rebalancing_plan(current_values, current_quantities, latest_prices, target)

        self.assertEqual(plan.index.name, "Symbol")
        # Total value 400 -> 200/200 target.
        self.assertAlmostEqual(plan.loc["A", "Δ Value"], 100.0)
        self.assertAlmostEqual(plan.loc["B", "Δ Value"], -100.0)
        self.assertEqual(plan.loc["A", "Action"], "Buy")
        self.assertEqual(plan.loc["B", "Action"], "Sell")
        # A: target 200/10 = 20 shares (from 10) -> +10; B: 200/20 = 10 (from 15) -> -5
        self.assertAlmostEqual(plan.loc["A", "Δ Qty"], 10.0)
        self.assertAlmostEqual(plan.loc["B", "Δ Qty"], -5.0)

    def test_already_balanced_is_hold(self):
        values = pd.Series({"A": 200.0, "B": 200.0})
        quantities = pd.Series({"A": 20.0, "B": 10.0})
        prices = pd.Series({"A": 10.0, "B": 20.0})
        plan = rebalancing_plan(values, quantities, prices, pd.Series({"A": 0.5, "B": 0.5}))
        self.assertTrue((plan["Action"] == "Hold").all())

    def test_empty_target(self):
        self.assertTrue(rebalancing_plan(pd.Series(dtype=float), pd.Series(dtype=float),
                                          pd.Series(dtype=float), pd.Series(dtype=float)).empty)


class TestTurnover(unittest.TestCase):
    def test_one_way_turnover(self):
        current_values = pd.Series({"A": 100.0, "B": 300.0})
        plan = rebalancing_plan(
            current_values,
            pd.Series({"A": 10.0, "B": 15.0}),
            pd.Series({"A": 10.0, "B": 20.0}),
            pd.Series({"A": 0.5, "B": 0.5}),
        )
        self.assertAlmostEqual(turnover(plan), 0.25)

    def test_empty_plan(self):
        self.assertEqual(turnover(pd.DataFrame()), 0.0)


if __name__ == "__main__":
    unittest.main()
