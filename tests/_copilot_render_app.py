"""AppTest harness that renders every Co-Pilot analytics section offline.

The real page fetches prices, fundamentals, statements, surveillance lists and
the earnings calendar from Yahoo/NSE. The test suite must never touch the
network, so each loader is replaced here with a hand-built frame and the script
renders whichever section the harness control selects.

This is a script for ``AppTest.from_file``, not a test module (the leading
underscore keeps pytest from collecting it); ``test_portfolio_analytics.py``
drives it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PAGE = Path(__file__).resolve().parent.parent / "pages" / "portfolio_analysis.py"

_spec = importlib.util.spec_from_file_location("co_pilot_under_test", PAGE)
co_pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(co_pilot)

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]
DATES = pd.date_range("2025-01-01", periods=180, freq="B", name="Date")
_rng = np.random.default_rng(7)

PRICES = pd.DataFrame(
    {symbol: 100 + _rng.normal(0, 1, len(DATES)).cumsum() for symbol in SYMBOLS},
    index=DATES,
)
BENCHMARK = pd.Series(
    1000 + _rng.normal(0, 1, len(DATES)).cumsum(), index=DATES, name="NIFTY 50"
)

HOLDINGS = pd.DataFrame(
    {
        "Symbol": SYMBOLS,
        "Total Quantity": [10, 20, 5, 8],
        "Invested Value": [1_000.0, 4_000.0, 500.0, 1_600.0],
        "Current Value": [1_100.0, 3_800.0, 600.0, 1_500.0],
    }
)

# One row per symbol, covering every field the valuation and red-flag views read.
COMPANY = pd.DataFrame(
    {
        "P/E (trailing)": [12.0, -3.0, 40.0, 25.0],
        "P/E (forward)": [11.0, -2.5, 35.0, 22.0],
        "P/B": [1.2, 0.8, 4.0, 3.0],
        "EPS (trailing)": [8.5, -1.0, 2.0, 1.5],
        "Dividend yield (%)": [2.0, 0.0, 0.5, 1.0],
        "Market cap": [1e10, 5e9, 2e10, 8e9],
        "Debt to equity (%)": [40.0, 300.0, 20.0, 90.0],
        "Current ratio": [1.8, 0.7, 2.2, 1.1],
        "Profit margin": [0.12, -0.05, 0.20, 0.08],
        "Operating margin": [0.15, -0.02, 0.25, 0.10],
        "Revenue growth": [0.10, -0.08, 0.05, 0.02],
        "Earnings growth": [0.12, -0.20, 0.06, 0.01],
        "Free cash flow": [2e8, -1e7, 5e8, 1e7],
        "Net income": [1e8, -2e7, 4e8, 3e7],
    },
    index=pd.Index(SYMBOLS, name="Symbol"),
)

# Includes one symbol with no score, so the "not enough statement data" path is
# exercised alongside the scored ones.
Z_SCORES = pd.DataFrame(
    {
        "Z-score": [3.4, 1.2, 2.5, np.nan],
        "Zone": ["Safe", "Distress", "Grey", None],
        "Total assets": [1e10, 5e9, 2e10, 8e9],
        "Total liabilities": [4e9, 4.5e9, 5e9, 3e9],
        "EBIT": [1.5e9, -1e8, 2e9, 4e8],
    },
    index=pd.Index(SYMBOLS, name="Symbol"),
)

SURVEILLANCE = pd.DataFrame(
    [
        {
            "Symbol": "BBB",
            "Company": "BBB Ltd",
            "List": "ASM",
            "Stage": "Stage I",
            "Code": "LTASM - I (13)",
            "Updated": "15-Oct-2026",
        },
        {
            "Symbol": "CCC",
            "Company": "CCC Ltd",
            "List": "GSM",
            "Stage": "Stage VI",
            "Code": "GSM - 0",
            "Updated": "15-Oct-2026",
        },
    ]
)

EARNINGS = pd.DataFrame(
    {
        "Symbol": SYMBOLS,
        "Date": pd.to_datetime(["2026-10-20", "2026-11-05", "2027-03-01", "2026-12-15"]),
        "Days away": [5, 21, 137, 61],
        "EPS estimate": [4.0, 2.5, 1.0, 3.0],
        "Revenue estimate": [1.2e9, 8e8, 4e8, 9e8],
    }
)

# The page resolves these as module globals, so replacing them is all it takes
# to keep the harness offline.
co_pilot.load_company_data = lambda symbols: COMPANY
co_pilot.load_default_risk = lambda symbols, market_caps: Z_SCORES
co_pilot.load_surveillance = lambda: SURVEILLANCE
co_pilot.load_earnings = lambda symbols: EARNINGS

_returns = co_pilot.compute_returns(PRICES)
_usable = [
    column
    for column in _returns.columns
    if _returns[column].notna().sum() >= co_pilot.MIN_OBSERVATIONS
]
_weights = HOLDINGS.set_index("Symbol")["Invested Value"]

context = co_pilot.AnalyticsContext(
    filtered_df=HOLDINGS,
    usable=_usable,
    returns=_returns[_usable],
    weights=_weights,
    portfolio_returns=co_pilot.weighted_portfolio_returns(_returns[_usable], _weights),
    prices=PRICES,
    benchmark=BENCHMARK,
)

section = st.segmented_control(
    "Harness section",
    co_pilot.ANALYTICS_SECTIONS,
    default=co_pilot.ANALYTICS_SECTIONS[0],
    key="harness_section",
)
co_pilot.SECTIONS[section or co_pilot.ANALYTICS_SECTIONS[0]](context)
