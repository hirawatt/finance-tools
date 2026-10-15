"""Target-allocation and rebalancing helpers for the Co-Pilot.

Everything here is a pure function over pandas objects so it can be unit-tested
without Streamlit or network access. The page fetches prices and handles display.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

STRATEGIES = ["Equal weight", "Inverse volatility", "Risk parity"]


def equal_weights(columns: Sequence[str]) -> pd.Series:
    """Naive 1/N allocation."""
    columns = list(columns)
    if not columns:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / len(columns), index=columns)


def inverse_volatility_weights(returns: pd.DataFrame) -> pd.Series:
    """Weight inversely to each holding's volatility (naive risk parity)."""
    if returns is None or returns.empty:
        return pd.Series(dtype=float)

    volatility = returns.std().replace(0, np.nan).dropna()
    if volatility.empty:
        return pd.Series(dtype=float)

    inverse = 1.0 / volatility
    return inverse / inverse.sum()


def risk_parity_weights(returns: pd.DataFrame) -> pd.Series:
    """Weights where every holding contributes equally to portfolio risk.

    Uses the convex log-barrier formulation of Spinu (2013): minimising
    ``0.5 * w'Σw - Σ b_i·log(w_i)`` with ``b_i = 1/n`` has a unique interior
    solution whose normalised weights equalise total risk contributions
    ``w_i * (Σw)_i / sqrt(w'Σw)``.
    """
    if returns is None or returns.empty:
        return pd.Series(dtype=float)

    covariance = returns.cov()
    columns = list(covariance.columns)
    n = len(columns)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series([1.0], index=columns)

    values = covariance.to_numpy()
    budget = np.full(n, 1.0 / n)

    def objective(weights: np.ndarray) -> float:
        return float(0.5 * weights @ values @ weights - np.sum(budget * np.log(weights)))

    # Imported lazily: only risk parity needs the optimiser.
    from scipy.optimize import minimize

    x0 = np.full(n, 1.0 / n)
    result = minimize(objective, x0, method="L-BFGS-B", bounds=[(1e-8, None)] * n)

    weights = np.clip(result.x if np.all(np.isfinite(result.x)) else x0, 0.0, None)
    total = weights.sum()
    if total <= 0:
        return equal_weights(columns)
    return pd.Series(weights / total, index=columns)


def apply_weight_cap(weights: pd.Series, max_weight: float) -> pd.Series:
    """Cap any single weight at ``max_weight``, redistributing the excess.

    Excess is spread across the holdings still under the cap proportional to
    their remaining headroom (water-filling), so it converges. When the cap is
    below ``1 / n`` it is infeasible, so equal weights are used instead.
    """
    if weights is None or weights.empty:
        return pd.Series(dtype=float)

    capped = weights.astype(float).copy()
    n = len(capped)
    effective_cap = max(max_weight, 1.0 / n)

    for _ in range(n + 1):
        over = capped > effective_cap + 1e-12
        if not over.any():
            break
        excess = float((capped[over] - effective_cap).sum())
        capped[over] = effective_cap
        under = ~over
        if not under.any():
            break
        headroom = (effective_cap - capped[under]).clip(lower=0.0)
        room = headroom.sum()
        if room <= 0:
            break
        capped[under] += excess * headroom / room

    total = capped.sum()
    return capped / total if total > 0 else capped


def target_weights(
    returns: pd.DataFrame, strategy: str, max_weight: Optional[float] = None
) -> pd.Series:
    """Target weights for ``strategy``, optionally capped per holding."""
    if strategy == "Equal weight":
        weights = equal_weights(returns.columns if returns is not None else [])
    elif strategy == "Inverse volatility":
        weights = inverse_volatility_weights(returns)
    elif strategy == "Risk parity":
        weights = risk_parity_weights(returns)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    if weights.empty:
        return weights
    if max_weight is not None:
        weights = apply_weight_cap(weights, max_weight)
    return weights / weights.sum()


def rebalancing_plan(
    current_values: pd.Series,
    current_quantities: pd.Series,
    latest_prices: pd.Series,
    target_weights: pd.Series,
) -> pd.DataFrame:
    """Turn target weights into concrete quantity and value trades.

    ``current_values``/``current_quantities`` are per symbol current market value
    and shares held; ``latest_prices`` is the most recent close per symbol;
    ``target_weights`` are the desired fractions. Rows are ordered by the size of
    the required trade.
    """
    if target_weights is None or target_weights.empty:
        return pd.DataFrame()

    symbols = target_weights.index
    values = current_values.reindex(symbols).fillna(0.0)
    quantities = current_quantities.reindex(symbols).fillna(0.0)
    prices = latest_prices.reindex(symbols)

    total_value = values.sum()
    target_values = target_weights * total_value

    rounded_targets = np.where(
        prices.notna() & (prices > 0), (target_values / prices).round(), quantities
    )
    target_quantities = pd.Series(rounded_targets, index=symbols)

    delta_value = target_values - values
    delta_quantity = target_quantities - quantities

    plan = pd.DataFrame(
        {
            "Price": prices,
            "Current Qty": quantities,
            "Target Qty": target_quantities,
            "Δ Qty": delta_quantity,
            "Current Value": values,
            "Target Value": target_values,
            "Δ Value": delta_value,
            "Current %": values / total_value * 100 if total_value else values * 0,
            "Target %": target_weights * 100,
        }
    )
    plan["Action"] = np.where(
        delta_value > 1e-6, "Buy", np.where(delta_value < -1e-6, "Sell", "Hold")
    )
    plan.index.name = "Symbol"
    return plan.reindex(plan["Δ Value"].abs().sort_values(ascending=False).index)


def turnover(plan: pd.DataFrame) -> float:
    """One-way turnover as a fraction of portfolio value (buys ≈ sells)."""
    if plan is None or plan.empty:
        return 0.0
    total = plan["Current Value"].sum()
    if total == 0:
        return 0.0
    return float(plan.loc[plan["Δ Value"] > 0, "Δ Value"].sum() / total)
