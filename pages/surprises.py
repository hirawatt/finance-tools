"""Due Diligence — snapshot-only screens for surprises and unusual activity.

Every screen reads the nightly snapshot: end-of-day closes and volume from the
prices job, and the option chain from NSE's F&O bhavcopy. Nothing on this page
fetches live, so it is as fast as the snapshot and never depends on NSE or Yahoo
being reachable at request time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Tuple

import pandas as pd
import streamlit as st

from utils import charts, snapshot, theme
from utils.options import (
    INDEX_SYMBOLS,
    implied_forward,
    oi_surges,
    parity_breaks,
    put_call_ratio,
)
from utils.pairs import candidate_pairs, rank_pairs
from utils.snapshot_store import snapshot_store
from utils.volume import volume_anomalies
from utils.watchlists import read_watchlists, watchlist_stamp

WATCHLIST_DIR = Path("indices")
ALL_WATCHLISTS = "All watchlists"

# The cross-market checks this desk runs, in display order. Each item is a
# Material Symbols name, a title and a one-line blurb (see utils/theme.py).
SCREENS = (
    ("compare_arrows", "Options pricing mismatch", "Put-call parity breaks that shouldn't be there."),
    ("difference", "Unusual moves in pairs", "Twin stocks drifting apart beyond their usual spread."),
    ("monitoring", "Unusual volume in stocks", "Cash-market prints far above the recent average."),
    ("candlestick_chart", "Unusual volume in options", "Open-interest and volume surges in the derivatives book."),
)
SECTION_TITLES = tuple(title for _, title, _ in SCREENS)
BLURBS = {title: body for _, title, body in SCREENS}

NO_SNAPSHOT = (
    "No snapshot covers this yet. The nightly job writes it after the market "
    "closes; this page never fetches live."
)


@st.cache_data(show_spinner=False)
def _watchlists(stamp: float) -> Dict[str, Tuple[str, ...]]:
    """The curated watchlists in ``indices/``, as ordered symbol tuples.

    ``stamp`` is the directory's latest mtime, so an edit made on the Index
    Creator page invalidates this entry rather than leaving the screens reading
    the pre-edit universe for an hour.
    """
    return read_watchlists(WATCHLIST_DIR)


def load_watchlists() -> Dict[str, Tuple[str, ...]]:
    """The watchlists as they are on disk right now."""
    return _watchlists(watchlist_stamp(WATCHLIST_DIR))


@st.cache_data(ttl=3600, show_spinner="Reading the nightly snapshot…")
def load_prices(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """End-of-day closes from the snapshot (never a live fetch)."""
    return snapshot.load_snapshot_prices(symbols, period="1y", store=snapshot_store())


@st.cache_data(ttl=3600, show_spinner="Reading the nightly snapshot…")
def load_volumes(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """End-of-day traded volume from the snapshot (never a live fetch)."""
    return snapshot.load_volumes(symbols, period="1y", store=snapshot_store())


@st.cache_data(ttl=3600, show_spinner="Reading the options snapshot…")
def load_chain() -> pd.DataFrame:
    """The end-of-day option chain from the snapshot (never a live fetch)."""
    return snapshot.load_options(store=snapshot_store())


@st.cache_data(ttl=3600, show_spinner=False)
def load_sectors() -> pd.DataFrame:
    """Sector and industry lookup for the pairs screen."""
    return pd.read_csv("./data/stock-sector.csv").rename(columns={"NSE code": "Symbol"})


def universe_symbols(
    selection: str, watchlists: Dict[str, Tuple[str, ...]]
) -> Tuple[str, ...]:
    """The ordered, de-duplicated symbol tuple for a watchlist selection."""
    if selection == ALL_WATCHLISTS:
        symbols = [symbol for names in watchlists.values() for symbol in names]
    else:
        symbols = list(watchlists.get(selection, ()))
    return tuple(dict.fromkeys(symbols))


def table(
    frame: pd.DataFrame, formats: Dict[str, str] | None = None, *, alt: str
) -> None:
    """Render a dataframe with number columns formatted through ``column_config``.

    ``alt`` names the table for assistive technology, so every call has to say
    what its rows are.
    """
    config = None
    if formats:
        config = {
            column: st.column_config.NumberColumn(format=theme.printf_format(pattern))
            for column, pattern in formats.items()
            if column in frame.columns
        }
    st.dataframe(frame, hide_index=True, column_config=config, alt=alt)


def _as_of(frame: pd.DataFrame) -> str:
    """The snapshot's trade date, when the frame carries one."""
    if "Date" in frame.columns and not frame["Date"].dropna().empty:
        return str(frame["Date"].dropna().max())
    return "the last snapshot"


def _parity_figure(
    subset: pd.DataFrame, spot: float | None
) -> tuple[object, str] | tuple[None, None]:
    """Implied forward against strike for the nearest expiry.

    Put-call parity says the synthetic forward (``strike + call − put``) should
    sit on one level for every strike of an expiry: a flat line. Plotting it
    turns a pricing mismatch into a visible outlier rather than a table lookup.
    """
    frame = subset.copy()
    frame["CE Close"] = pd.to_numeric(frame["CE Close"], errors="coerce")
    frame["PE Close"] = pd.to_numeric(frame["PE Close"], errors="coerce")
    frame["Implied forward"] = implied_forward(frame)
    frame = frame[
        frame["CE Close"].gt(0) & frame["PE Close"].gt(0) & frame["Implied forward"].notna()
    ]
    if frame.empty:
        return None, None

    expiry = sorted(frame["Expiry"].dropna().unique())[0]
    frame = frame[frame["Expiry"] == expiry].sort_values("Strike")

    futures = (
        pd.to_numeric(frame["Future close"], errors="coerce").dropna()
        if "Future close" in frame.columns
        else pd.Series(dtype=float)
    )
    reference = (
        float(futures.iloc[0])
        if not futures.empty
        else float(frame["Implied forward"].median())
    )

    fig = charts.scatter(
        frame["Strike"],
        frame["Implied forward"],
        x_title="Strike",
        y_title="Implied forward (₹)",
        x_fmt="{:,.0f}",
        y_fmt="{:,.0f}",
        x_ref=float(spot) if spot else None,
        y_ref=reference,
        height=340,
    )
    return fig, expiry


def render_options_mismatch(universe: Tuple[str, ...]) -> None:
    """Put-call parity breaks across an index's EOD option chain."""
    chain = load_chain()
    if chain.empty:
        st.info(NO_SNAPSHOT)
        return

    indices = [symbol for symbol in INDEX_SYMBOLS if symbol in set(chain["Symbol"])]
    if not indices:
        st.info(NO_SNAPSHOT)
        return

    left, middle, right = st.columns(3)
    underlying = left.selectbox("Index", indices, key="dd-parity-underlying")
    min_oi = middle.number_input(
        "Minimum open interest", value=1000, min_value=0, step=500, key="dd-parity-oi"
    )
    deviation = right.slider(
        "Flag deviation beyond (% of spot)",
        min_value=0.1,
        max_value=3.0,
        value=0.5,
        step=0.1,
        key="dd-parity-dev",
    )

    subset = chain[chain["Symbol"] == underlying]
    spot = subset["Underlying price"].dropna()
    breaks = parity_breaks(subset, min_oi=min_oi, max_deviation=deviation / 100)

    theme.metric_row(
        (
            ("Index", underlying),
            ("Spot", f"{spot.iloc[-1]:,.2f}" if not spot.empty else "–"),
            ("Expiries", f"{subset['Expiry'].nunique()}"),
            ("Breaks found", f"{len(breaks)}"),
        )
    )

    spot_value = float(spot.iloc[-1]) if not spot.empty else None
    fig, expiry = _parity_figure(subset, spot_value)
    if fig is not None:
        theme.chart(
            fig,
            alt=(
                "Implied forward from put-call parity against strike for one expiry, "
                "with the reference forward as a horizontal line"
            ),
        )
        st.caption(
            f"Nearest expiry {expiry}: parity says every strike's synthetic forward "
            "should sit on the reference line; points off it are the mispricing."
        )

    if breaks.empty:
        st.success(
            "No strike is priced away from its expiry's forward beyond the "
            "threshold and liquidity floor."
        )
    else:
        display = breaks.copy()
        display["Deviation %"] = display["Deviation %"] * 100
        table(
            display,
            {
                "CE Close": "{:,.2f}",
                "PE Close": "{:,.2f}",
                "CE OI": "{:,.0f}",
                "PE OI": "{:,.0f}",
                "Implied forward": "{:,.1f}",
                "Reference forward": "{:,.1f}",
                "Deviation": "{:,.1f}",
                "Deviation %": "{:,.2f}%",
            },
            alt="Strikes priced away from their expiry's implied forward",
        )

    st.caption(
        f"As of {_as_of(subset)}. A strike's synthetic forward is "
        "strike + call - put; the reference is the expiry's futures close where "
        "one traded, else the median of its liquid strikes. Index options are "
        "European, so any gap is a real mispricing or a stale quote."
    )


def render_volume_stocks(universe: Tuple[str, ...]) -> None:
    """Cash-market names trading far above their own recent volume."""
    volumes = load_volumes(universe)
    if volumes.empty:
        st.info(NO_SNAPSHOT)
        return

    closes = load_prices(tuple(volumes.columns))
    left, right = st.columns(2)
    lookback = left.slider(
        "Baseline sessions", min_value=5, max_value=60, value=20, key="dd-vol-lookback"
    )
    threshold = right.slider(
        "Flag above (x average)",
        min_value=1.5,
        max_value=10.0,
        value=3.0,
        step=0.5,
        key="dd-vol-threshold",
    )

    found = volume_anomalies(
        volumes, closes, lookback=lookback, threshold=threshold, min_turnover=1e7
    )

    theme.metric_row(
        (
            ("Symbols screened", f"{volumes.shape[1]}"),
            ("Sessions", f"{len(volumes)}"),
            ("Anomalies", f"{len(found)}"),
        )
    )

    if not found.empty:
        returns_pct = (found["Return"] * 100).fillna(0.0)
        theme.chart(
            charts.scatter(
                found["Ratio"],
                returns_pct,
                labels=found["Symbol"],
                sizes=found["Turnover"].fillna(0.0).clip(lower=0.0),
                color=[
                    charts.GAIN if value >= 0 else charts.LOSS for value in returns_pct
                ],
                x_title="Volume vs average (x)",
                y_title="Return (%)",
                x_fmt="{:,.1f}",
                y_fmt="{:+,.1f}",
                x_ref=threshold,
                y_ref=0.0,
                height=420,
            ),
            alt=(
                "Each volume spike plotted by how many times its average it traded "
                "against the session's price return, sized by turnover"
            ),
        )
        st.caption(
            "Marker area is rupee turnover and the dotted vertical line is the flag "
            "threshold, so a spike that came with a real move stands out from one "
            "that did not."
        )

    if found.empty:
        st.success("No name traded above the threshold in the latest session.")
    else:
        display = found.copy()
        display["Return"] = display["Return"] * 100
        display = display.rename(columns={"Return": "Return %"})
        table(
            display,
            {
                "Volume": "{:,.0f}",
                "Average volume": "{:,.0f}",
                "Ratio": "{:,.1f}",
                "Z-score": "{:,.1f}",
                "Return %": "{:,.2f}%",
                "Turnover": "{:,.0f}",
            },
            alt="Symbols trading above their average volume, with the session's price move",
        )

    st.caption(
        "The latest session's volume against the symbol's own trailing average, "
        "with a turnover floor so illiquid names do not dominate. A spike alone "
        "is not a signal — check it against the price move (Return %)."
    )


def render_option_volume(universe: Tuple[str, ...]) -> None:
    """Fresh positioning in the derivatives book, by OI change and volume."""
    chain = load_chain()
    if chain.empty:
        st.info(NO_SNAPSHOT)
        return

    left, right = st.columns(2)
    index_only = left.toggle("Index options only", value=True, key="dd-opt-index")
    top = right.slider(
        "Contracts to show", min_value=5, max_value=50, value=15, key="dd-opt-top"
    )

    surges = oi_surges(chain, index_only=index_only, top=top)

    theme.metric_row(
        (
            ("Underlyings", f"{chain['Symbol'].nunique()}"),
            ("Expiries", f"{chain['Expiry'].nunique()}"),
            ("Contract rows", f"{len(chain):,}"),
        )
    )

    if not surges.empty:
        contracts = [
            f"{row.Symbol} · {row.Expiry} · {row.Strike:,.0f} {row.Type}"
            for row in surges.itertuples()
        ]
        type_color = {"CE": charts.CATEGORICAL[0], "PE": charts.CATEGORICAL[2]}
        theme.chart(
            charts.barh(
                contracts,
                surges["OI change"].to_numpy(),
                value_fmt="{:+,.0f}",
                colors=[type_color.get(kind, charts.MUTED) for kind in surges["Type"]],
                hover_units=" contracts",
                x_title="Change in open interest",
                height=max(300, 30 * len(surges) + 60),
            ),
            alt="Contracts ranked by the session's change in open interest, blue for calls and amber for puts",
        )

    if surges.empty:
        st.success("No fresh positioning stands out in the snapshot.")
    else:
        table(
            surges,
            {
                "Close": "{:,.2f}",
                "OI": "{:,.0f}",
                "OI change": "{:,.0f}",
                "Volume": "{:,.0f}",
                "Buildup": "{:,.2f}",
            },
            alt="Contracts with the largest change in open interest",
        )

    with st.expander("Put-call ratio by expiry"):
        ratios = put_call_ratio(chain, index_only=index_only)
        if ratios.empty:
            st.info(NO_SNAPSHOT)
        else:
            table(
                ratios,
                {
                    "CE OI": "{:,.0f}",
                    "PE OI": "{:,.0f}",
                    "Put-call ratio": "{:,.2f}",
                    "CE Volume": "{:,.0f}",
                    "PE Volume": "{:,.0f}",
                },
                alt="Put-call ratio by underlying and expiry",
            )
            labels = [
                f"{row.Symbol} · {row.Expiry}" for row in ratios.itertuples()
            ]
            theme.chart(
                charts.vertical_bar(
                    labels,
                    ratios["Put-call ratio"].to_numpy(),
                    value_fmt="{:.2f}",
                    color=[
                        charts.WARN if value > 1 else charts.ACCENT
                        for value in ratios["Put-call ratio"]
                    ],
                    y_title="Put-call ratio",
                    reference=1.0,
                    reference_label="Neutral 1.0",
                    height=320,
                ),
                alt="Put-call ratio by underlying and expiry, with the neutral 1.0 line marked",
            )

    st.caption(
        f"As of {_as_of(chain)}. Buildup is the session's change in open interest "
        "over the previous book: a high reading is fresh positioning, not a "
        "recommendation. A larger reading needs a larger follow-through."
    )


def render_pairs(universe: Tuple[str, ...]) -> None:
    """Same-industry pairs whose spread has stretched."""
    prices = load_prices(universe)
    if prices.empty:
        st.info(NO_SNAPSHOT)
        return

    sectors = load_sectors()
    pairs = candidate_pairs(sectors, symbols=prices.columns)
    if not pairs:
        st.info("No same-industry pairs in this universe.")
        return

    left, right = st.columns(2)
    lookback = left.slider(
        "Spread window (sessions)", min_value=30, max_value=120, value=60, key="dd-pair-lookback"
    )
    threshold = right.slider(
        "Flag beyond (z-score)",
        min_value=1.0,
        max_value=4.0,
        value=2.0,
        step=0.25,
        key="dd-pair-threshold",
    )

    ranked = rank_pairs(prices, pairs, lookback=lookback, threshold=threshold)

    theme.metric_row(
        (
            ("Tradeable symbols", f"{prices.shape[1]}"),
            ("Candidate pairs", f"{len(pairs):,}"),
            ("Stretched", f"{len(ranked)}"),
        )
    )

    if not ranked.empty:
        labels = [
            f"{a} / {b}"
            for a, b in zip(ranked["Symbol A"], ranked["Symbol B"])
        ]
        fig = charts.barh(
            labels,
            ranked["Spread z"].to_numpy(),
            value_fmt="{:+.2f}",
            color=charts.ACCENT,
            x_title="Spread z-score",
            threshold=threshold,
            threshold_label=f"±{threshold:.2f} z",
            height=max(280, 34 * len(ranked) + 60),
        )
        fig.add_vline(
            x=-threshold,
            line=dict(color=charts.MUTED, width=1.4, dash="dash"),
        )
        theme.chart(
            fig,
            alt="Stretched pairs ranked by how many standard deviations their spread sits from its own mean",
        )
        st.caption(
            "A positive z means the first symbol is rich against the second; the "
            "dashed lines are the flag thresholds either side of zero."
        )

    if ranked.empty:
        st.success("No correlated pair's spread is stretched beyond the threshold.")
    else:
        table(
            ranked,
            {
                "Beta": "{:,.2f}",
                "Correlation": "{:,.2f}",
                "Spread z": "{:,.2f}",
                "Spread": "{:,.3f}",
            },
            alt="Same-industry pairs ranked by how stretched their spread is",
        )

    st.caption(
        "Each pair is hedged by the log-price beta; the z-score is how far the "
        "latest spread sits from its own window. A rich A against B is a "
        "relative-value candidate, not a standalone trade."
    )


RENDERERS: Dict[str, Callable[[Tuple[str, ...]], None]] = {
    "Options pricing mismatch": render_options_mismatch,
    "Unusual moves in pairs": render_pairs,
    "Unusual volume in stocks": render_volume_stocks,
    "Unusual volume in options": render_option_volume,
}


@st.fragment
def render_section(section: str, universe: Tuple[str, ...]) -> None:
    """The selected screen, as a fragment.

    The screens' sliders only move their own chart and table, so rerunning just
    this block keeps the header and the universe picker still while a window or
    threshold is dragged.
    """
    st.caption(BLURBS[section])
    RENDERERS[section](universe)


def main() -> None:
    theme.page_header(
        "Due Diligence",
        "Surfaces worth a closer look before you trade — unusual pricing and "
        "volume, read from the nightly snapshot after the market closes.",
    )

    watchlists = load_watchlists()
    if not watchlists:
        st.warning("No watchlists found in indices/.")
        return

    with st.sidebar:
        st.subheader("Due Diligence")
        selection = st.selectbox(
            "Universe", (ALL_WATCHLISTS, *watchlists), key="dd-universe"
        )
    universe = universe_symbols(selection, watchlists)

    section = st.segmented_control(
        "Check",
        SECTION_TITLES,
        default=SECTION_TITLES[0],
        key="dd-section",
        label_visibility="collapsed",
    )
    section = section or SECTION_TITLES[0]
    render_section(section, universe)


if __name__ == "__main__":
    main()
