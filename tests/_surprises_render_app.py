"""AppTest harness that renders every Due Diligence section offline.

The real page reads the nightly snapshot; the test suite must never touch the
network or a real snapshot, so each loader is replaced here with a hand-built
frame and the harness renders whichever section the control selects.

This is a script for ``AppTest.from_file``, not a test module (the leading
underscore keeps pytest from collecting it); ``test_surprises.py`` drives it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from utils.options import parse_fo_bhavcopy

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "surprises.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fo_bhavcopy_sample.csv"

_spec = importlib.util.spec_from_file_location("surprises_under_test", PAGE)
page = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(page)

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]
DATES = pd.date_range("2025-01-01", periods=120, freq="B", name="Date")
_rng = np.random.default_rng(3)
_common = _rng.normal(0, 0.01, len(DATES))

PRICES = pd.DataFrame(
    {
        "AAA": 1000 * np.cumprod(1 + _common + _rng.normal(0, 0.002, len(DATES))),
        "BBB": 1000 * np.cumprod(1 + _common + _rng.normal(0, 0.002, len(DATES))),
        "CCC": 1000 * np.cumprod(1 + _rng.normal(0, 0.015, len(DATES))),
        "DDD": 1000 * np.cumprod(1 + _rng.normal(0, 0.015, len(DATES))),
    },
    index=DATES,
)
PRICES.iloc[-1, PRICES.columns.get_loc("AAA")] *= 1.06  # stretch the AAA/BBB spread

VOLUMES = pd.DataFrame(10_000.0, index=DATES, columns=SYMBOLS)
VOLUMES.iloc[-1, VOLUMES.columns.get_loc("AAA")] = 100_000.0

SECTORS = pd.DataFrame(
    {"Symbol": SYMBOLS, "Industry": ["Cement", "Cement", "IT", "IT"]}
)

CHAIN = parse_fo_bhavcopy(pd.read_csv(FIXTURE))

# The page resolves these as module globals, so replacing them is all it takes
# to keep the harness offline.
page.load_prices = lambda symbols, period="1y": PRICES
page.load_volumes = lambda symbols, period="1y": VOLUMES
page.load_chain = lambda: CHAIN
page.load_sectors = lambda: SECTORS
page.load_watchlists = lambda: {"sample": tuple(SYMBOLS)}

section = st.segmented_control(
    "Harness section",
    page.SECTION_TITLES,
    default=page.SECTION_TITLES[0],
    key="harness_section",
)
page.RENDERERS[section or page.SECTION_TITLES[0]](tuple(SYMBOLS))
