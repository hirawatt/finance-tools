"""Tests for utils.options (pure bhavcopy parsing and option analytics, no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils.options import (
    OPTION_COLUMNS,
    PARITY_COLUMNS,
    RATIO_COLUMNS,
    SURGE_COLUMNS,
    implied_forward,
    oi_surges,
    parse_fo_bhavcopy,
    parity_breaks,
    put_call_ratio,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fo_bhavcopy_sample.csv"
TRADE_DATE = "2026-10-16"
E1 = "2026-11-26"
E2 = "2026-12-31"


def _chain() -> pd.DataFrame:
    return parse_fo_bhavcopy(pd.read_csv(FIXTURE))


class TestParse:
    def test_returns_the_chain_columns(self):
        chain = _chain()
        assert list(chain.columns) == OPTION_COLUMNS
        assert not chain.empty

    def test_pivots_call_and_put_onto_one_row(self):
        chain = _chain()
        row = chain[(chain["Symbol"] == "NIFTY") & (chain["Expiry"] == E1) & (chain["Strike"] == 100)].iloc[0]
        assert row["CE Close"] == 4.0
        assert row["PE Close"] == 2.0
        assert row["CE OI"] == 5000
        assert row["PE OI"] == 5000

    def test_carries_the_trade_date_and_the_underlying_price(self):
        chain = _chain()
        assert set(chain["Date"]) == {TRADE_DATE}
        assert set(chain[chain["Symbol"] == "NIFTY"]["Underlying price"]) == {100.0}

    def test_merges_the_futures_close_as_the_forward(self):
        chain = _chain()
        assert chain[(chain["Symbol"] == "NIFTY") & (chain["Expiry"] == E1)]["Future close"].iloc[0] == 102
        assert chain[(chain["Symbol"] == "RELIANCE")]["Future close"].iloc[0] == 2510
        assert (chain[(chain["Symbol"] == "NIFTY") & (chain["Expiry"] == E2)]["Future close"].isna()).all()

    def test_drops_futures_and_other_non_options(self):
        chain = _chain()
        # BANKNIFTY appears only as a future in the fixture.
        assert "BANKNIFTY" not in set(chain["Symbol"])
        assert set(chain["Symbol"]) == {"NIFTY", "RELIANCE"}

    def test_accepts_missing_or_foreign_payloads(self):
        for payload in (None, pd.DataFrame(), pd.DataFrame({"nope": [1]})):
            frame = parse_fo_bhavcopy(payload)
            assert frame.empty
            assert list(frame.columns) == OPTION_COLUMNS


class TestImpliedForward:
    def test_parity_identity(self):
        chain = _chain()
        forward = implied_forward(chain)
        row = chain[(chain["Symbol"] == "NIFTY") & (chain["Expiry"] == E1) & (chain["Strike"] == 98)].index[0]
        assert forward.loc[row] == 98 + 9.0 - 2.5

    def test_empty(self):
        assert implied_forward(pd.DataFrame()).empty


class TestParityBreaks:
    def test_flags_only_the_mispriced_strikes(self):
        breaks = parity_breaks(_chain(), min_oi=1000)
        found = set(zip(breaks["Symbol"], breaks["Expiry"], breaks["Strike"]))
        assert found == {("NIFTY", E1, 98.0), ("NIFTY", E2, 98.0)}

    def test_uses_the_futures_close_when_present(self):
        breaks = parity_breaks(_chain(), min_oi=1000)
        first = breaks[(breaks["Expiry"] == E1)].iloc[0]
        assert first["Reference forward"] == 102
        assert first["Deviation"] == 2.5
        assert round(first["Deviation %"], 4) == 0.025

    def test_falls_back_to_the_median_without_a_future(self):
        breaks = parity_breaks(_chain(), min_oi=1000)
        second = breaks[(breaks["Expiry"] == E2)].iloc[0]
        assert second["Reference forward"] == 101
        assert second["Deviation"] == 3.0

    def test_liquidity_floor_excludes_thin_strikes(self):
        chain = _chain()
        thin = chain[(chain["Symbol"] == "NIFTY") & (chain["Strike"] == 102)].copy()
        assert thin["CE OI"].iloc[0] == 10
        assert parity_breaks(thin, min_oi=1000).empty

    def test_moneyness_band_excludes_far_strikes(self):
        chain = _chain()
        far = chain[(chain["Symbol"] == "RELIANCE")].copy()
        # All RELIANCE strikes are within 2% of spot, so a 0% band finds nothing.
        assert parity_breaks(far, max_moneyness=0.0).empty
        assert parity_breaks(far).empty  # and parity holds across the band

    def test_empty(self):
        assert list(parity_breaks(pd.DataFrame()).columns) == PARITY_COLUMNS


class TestOiSurges:
    def test_ranks_by_the_day_over_day_oi_change(self):
        surges = oi_surges(_chain(), top=5)
        assert list(surges.columns) == SURGE_COLUMNS
        top = surges.iloc[0]
        assert (top["Symbol"], top["Strike"], top["Type"]) == ("NIFTY", 98.0, "CE")
        assert top["OI change"] == 4000
        assert top["Buildup"] == 4.0  # 4000 change on a 1000 prior book

    def test_drops_contracts_that_never_traded(self):
        surges = oi_surges(_chain(), top=None)
        assert not ((surges["Symbol"] == "NIFTY") & (surges["Strike"] == 102)).any()

    def test_index_only(self):
        surges = oi_surges(_chain(), index_only=True, top=None)
        assert set(surges["Symbol"]) == {"NIFTY"}

    def test_empty(self):
        assert list(oi_surges(pd.DataFrame()).columns) == SURGE_COLUMNS


class TestPutCallRatio:
    def test_sums_the_book_per_expiry(self):
        ratios = put_call_ratio(_chain())
        assert list(ratios.columns) == RATIO_COLUMNS
        row = ratios[(ratios["Symbol"] == "NIFTY") & (ratios["Expiry"] == E1)].iloc[0]
        assert row["CE OI"] == 20010
        assert row["PE OI"] == 20010
        assert row["Put-call ratio"] == 1.0

    def test_index_only(self):
        ratios = put_call_ratio(_chain(), index_only=True)
        assert set(ratios["Symbol"]) == {"NIFTY"}

    def test_empty(self):
        assert list(put_call_ratio(pd.DataFrame()).columns) == RATIO_COLUMNS
