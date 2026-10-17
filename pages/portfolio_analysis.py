"""Co-Pilot — portfolio analytics, risk and rebalancing.

Charts are built with :mod:`utils.charts` and the shared display config in
:mod:`utils.theme`, so every view uses the same palette, axes and hover grammar.
Analytics sections are one renderer per section over a shared
:class:`AnalyticsContext`, registered in :data:`SECTIONS`.
"""

import streamlit as st
import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from utils import brokers, charts, holdings, portfolio_store, snapshot, theme
from utils.theme import printf_format
from utils.rebalancing import (
    STRATEGIES,
    rebalancing_plan,
    target_weights,
    turnover,
)
from utils.earnings import upcoming
from utils.forecasting import forecast_paths
from utils.market_data import (
    BENCHMARK_NAME,
    COMPANY_FIELDS,
    FUNDAMENTAL_FIELDS,
    MIN_OBSERVATIONS,
    PERCENT_METRICS,
    compute_beta,
    compute_returns,
    correlation_matrix,
    full_metrics_report,
    performance_summary,
    weighted_average_pe,
    weighted_portfolio_returns,
)
from utils.red_flags import detect_red_flags, flag_summary
from utils.surveillance import check_symbols


@st.cache_data(ttl=3600)
def load_sectors() -> pd.DataFrame:
    """Sector lookup used by the sector-allocation chart."""
    return pd.read_csv('./data/stock-sector.csv').rename(columns={"NSE code": "Symbol"})


@st.cache_data(ttl=3600)
def load_sample_holdings() -> pd.DataFrame:
    """The committed sample portfolio, read through the broker importer.

    Going through the same reader a real upload uses keeps one code path — and
    proves the importer works on every cold start.
    """
    data = Path('./data/holdings-sample.xlsx').read_bytes()
    return brokers.import_holdings(data, 'holdings-sample.xlsx').core


@st.cache_resource(show_spinner=False)
def snapshot_store():
    """Object storage holding the nightly market-data snapshot.

    Configured from the ``[snapshot]`` secrets table (or ``SNAPSHOT_*`` env
    vars), and degrading to a local directory when nothing is configured, in
    which case every loader simply falls back to live fetches.
    """
    try:
        secrets = st.secrets.to_dict()
    except Exception:  # no secrets file, or running outside Streamlit
        secrets = {}
    return snapshot.SnapshotConfig.from_secrets(secrets).store()


@st.cache_data(ttl=3600, max_entries=32, show_spinner="Fetching market data…")
def load_price_history(symbols: Tuple[str, ...], period: str) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Daily price history, served from the nightly snapshot where possible."""
    return snapshot.load_prices(symbols, period=period, store=snapshot_store())


@st.cache_data(ttl=3600, max_entries=32, show_spinner="Fetching fundamentals…")
def load_company_data(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Fundamentals (valuation + risk), served from the snapshot where possible."""
    return snapshot.load_company_data(symbols, COMPANY_FIELDS, store=snapshot_store())


@st.cache_data(ttl=21600, show_spinner="Fetching NSE surveillance lists…")
def load_surveillance() -> pd.DataFrame:
    """NSE ASM/GSM surveillance lists (refreshed daily)."""
    return snapshot.load_surveillance(store=snapshot_store())


@st.cache_data(ttl=21600, max_entries=32, show_spinner="Crunching company statements…")
def load_default_risk(symbols: Tuple[str, ...], market_caps: Dict[str, float]) -> pd.DataFrame:
    """Altman Z-scores for the given symbols, snapshot-first."""
    return snapshot.load_default_risk(
        symbols, pd.Series(market_caps), store=snapshot_store()
    )


@st.cache_data(ttl=3600, max_entries=32, show_spinner="Fetching earnings calendar…")
def load_earnings(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Upcoming earnings dates for the given symbols, snapshot-first."""
    return snapshot.load_earnings(symbols, store=snapshot_store())


# --------------------------------------------------------------------------- #
# Analytics: one renderer per section, over a shared, frozen context
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AnalyticsContext:
    """Everything the analytics sections read, computed once per render.

    Passing one context keeps the sections independent of each other and lets
    each one be read — and tested — on its own.
    """

    filtered_df: pd.DataFrame
    usable: list
    returns: pd.DataFrame
    weights: pd.Series
    portfolio_returns: pd.Series
    prices: pd.DataFrame
    benchmark: Optional[pd.Series]

    @property
    def symbols(self) -> Tuple[str, ...]:
        """The symbols, sorted — the key the cached loaders are called with."""
        return tuple(sorted(self.usable))


def load_or_empty(loader: Callable[..., pd.DataFrame], *args, what: str) -> pd.DataFrame:
    """Call a market-data loader, warning and returning an empty frame on failure.

    The analytics are advisory: an upstream outage shows a warning and an empty
    section rather than breaking the page.
    """
    try:
        frame = loader(*args)
    except Exception as e:  # network / parsing failures should not break the page
        st.warning(f"Could not fetch {what}: {e}")
        return pd.DataFrame()
    return frame if frame is not None else pd.DataFrame()


def fundamentals_for(ctx: AnalyticsContext) -> pd.DataFrame:
    """Company fundamentals, shared by the valuation and risk-flag sections."""
    return load_or_empty(load_company_data, ctx.symbols, what="fundamentals")


def table(
    data: pd.DataFrame,
    formats=None,
    *,
    hide_index: bool = False,
    alt: Optional[str] = None,
) -> None:
    """Render a dataframe, formatting numbers through ``column_config``.

    ``formats`` is either one format string for every column or a mapping of
    column to format string; the Python-style specs are translated to the
    printf style ``st.column_config.NumberColumn`` expects.
    """
    if formats is None:
        column_config = None
    elif isinstance(formats, dict):
        column_config = {
            column: st.column_config.NumberColumn(format=printf_format(pattern))
            for column, pattern in formats.items()
        }
    else:
        column_config = {
            column: st.column_config.NumberColumn(format=printf_format(formats))
            for column in data.columns
        }
    st.dataframe(
        data, hide_index=hide_index, column_config=column_config, alt=alt
    )


# --------------------------------------------------------------------------- #
# The portfolio at a glance: distribution and P&L
# --------------------------------------------------------------------------- #
def render_allocation(filtered_df: pd.DataFrame, df_with_sectors: pd.DataFrame) -> None:
    """The portfolio's shape: sector mix, holding ranking and where P&L came from.

    Two complementary views replace the old pair of pies: a donut answers the
    part-to-whole question (which sector am I actually in?), while a ranking bar
    answers the ordering question and carries each holding's P&L as colour. A
    third, signed bar isolates profit and loss — the view every broker console
    leads with.
    """
    total = float(filtered_df["Current Value"].sum())

    by_symbol = (
        filtered_df.groupby("Symbol")[["Current Value", "Invested Value"]].sum()
    )
    by_symbol["P&L"] = by_symbol["Current Value"] - by_symbol["Invested Value"]

    sector = df_with_sectors.copy()
    sector["Sector"] = sector["Sector"].fillna("Unclassified")
    by_sector = sector.groupby("Sector")["Current Value"].sum().sort_values(ascending=False)

    left, right = st.columns([1, 1.15])
    with left:
        st.subheader("Sector allocation")
        theme.chart(
            charts.donut(
                by_sector,
                max_slices=8,
                center_title="Portfolio",
                center_value=f"₹{total:,.0f}",
                value_fmt="₹{:,.0f}",
                height=340,
            ),
            alt="Invested value split by sector, with the portfolio total in the centre",
        )
    with right:
        st.subheader("Holdings by value")
        theme.chart(
            charts.barh(
                by_symbol.index,
                by_symbol["Current Value"],
                value_fmt="₹{:,.0f}",
                colors=[charts.GAIN if v >= 0 else charts.LOSS for v in by_symbol["P&L"]],
                x_title="Current value",
                height=max(260, 34 * len(by_symbol) + 50),
            ),
            alt="Current value of each holding, coloured green for a gain and red for a loss",
        )

    st.subheader("Profit & loss by holding")
    theme.chart(
        charts.diverging_barh(
            by_symbol.index,
            by_symbol["P&L"],
            value_fmt="₹{:+,.0f}",
            x_title="Profit & loss",
            height=max(260, 34 * len(by_symbol) + 50),
        ),
        alt="Profit and loss in rupees for each holding, green for profits and red for losses",
    )


# --------------------------------------------------------------------------- #
# Analytics sections
# --------------------------------------------------------------------------- #
def render_correlation(ctx: AnalyticsContext) -> None:
    """Correlation heatmap of the holdings' daily returns."""
    corr = correlation_matrix(ctx.returns)
    if corr.empty:
        st.info("Not enough overlapping history to compute correlations.")
        return

    theme.chart(
        charts.heatmap(corr, height=max(320, 42 * len(corr) + 90)),
        alt="Correlation heatmap of daily returns between the selected holdings",
    )

    if len(corr) > 1:
        upper = np.triu(np.ones(corr.shape), k=1).astype(bool)
        pairs = corr.where(upper).stack().dropna().sort_values()
        extremes = pd.concat([pairs.head(5), pairs.tail(5)]).drop_duplicates()
        labels = [f"{a} · {b}" for a, b in extremes.index]
        st.subheader("Strongest and weakest pairs")
        theme.chart(
            charts.barh(
                labels,
                extremes.to_numpy(),
                value_fmt="{:+.2f}",
                colors=[charts.GAIN if v >= 0 else charts.LOSS for v in extremes.to_numpy()],
                x_title="Correlation of daily returns",
                height=max(260, 30 * len(extremes) + 50),
            ),
            alt="The most positively and negatively correlated pairs of holdings",
        )
        st.caption(
            "Closer to +1 means the two move together; closer to −1 means they "
            "tend to move apart. Low or negative readings are what diversify a book."
        )


def _format_metric(label: str, value: float) -> str:
    """Format one performance metric for a KPI tile."""
    if pd.isna(value):
        return "–"
    if label in PERCENT_METRICS:
        return f"{value:.2%}"
    return f"{value:.2f}"


def render_beta(ctx: AnalyticsContext) -> None:
    """Per-holding beta, headline risk/return and the risk-return map."""
    if ctx.benchmark is not None and not ctx.benchmark.empty:
        beta = compute_beta(ctx.returns, ctx.benchmark)
        if beta.empty:
            st.info("Not enough overlap with the benchmark to compute beta.")
        else:
            theme.chart(
                charts.barh(
                    beta.index,
                    beta.to_numpy(),
                    value_fmt="{:.2f}",
                    color=charts.ACCENT,
                    threshold=1.0,
                    threshold_label="Market beta 1.0",
                    x_title="Beta",
                    height=max(260, 34 * len(beta) + 50),
                ),
                alt=f"Beta of each holding against {BENCHMARK_NAME}, with a reference line at 1",
            )
            st.caption(
                f"Beta vs {BENCHMARK_NAME}: above 1 moves more than the index, "
                "below 1 moves less. Bars are ranked so the market-sensitive names "
                "sit at the top."
            )
    else:
        st.info(f"{BENCHMARK_NAME} history unavailable; beta cannot be computed.")

    st.subheader("Value-weighted portfolio risk / return")
    summary = performance_summary(ctx.portfolio_returns)
    metrics = [
        (label, _format_metric(label, value)) for label, value in summary.items()
    ]
    theme.metric_row(metrics[:4])
    theme.metric_row(metrics[4:])

    st.subheader("Risk-return map")
    annualised = pd.DataFrame(
        {
            "Return": ctx.returns.mean() * 252 * 100,
            "Volatility": ctx.returns.std() * np.sqrt(252) * 100,
        }
    ).dropna()
    if annualised.empty:
        return

    benchmark_vol = None
    if ctx.benchmark is not None and not ctx.benchmark.empty:
        bench = ctx.benchmark.pct_change(fill_method=None).dropna()
        if len(bench) > MIN_OBSERVATIONS:
            benchmark_vol = float(bench.std() * np.sqrt(252) * 100)

    weights = ctx.weights.reindex(annualised.index).fillna(0.0).clip(lower=0.0)
    theme.chart(
        charts.scatter(
            annualised["Volatility"],
            annualised["Return"],
            labels=annualised.index,
            sizes=(weights + 1e-9).to_numpy(),
            x_title="Volatility (ann.)",
            y_title="Return (ann.)",
            x_fmt="{:,.1f}",
            y_fmt="{:,.1f}",
            y_ref=0.0,
            x_ref=benchmark_vol,
            height=400,
        ),
        alt="Annualised volatility against annualised return for each holding, sized by portfolio weight",
    )
    note = (
        f"Marker area is the holding's weight; the dotted vertical line is "
        f"{BENCHMARK_NAME}'s own volatility. Up and to the left is the better seat."
        if benchmark_vol is not None
        else "Marker area is the holding's weight. Up and to the left is the better seat."
    )
    st.caption(note)


def render_valuation(ctx: AnalyticsContext) -> None:
    """Valuation multiples and the value-weighted portfolio P/E."""
    company_data = fundamentals_for(ctx)
    if company_data.empty:
        st.info("No valuation data available for the selected symbols.")
        return

    fundamentals = company_data[list(FUNDAMENTAL_FIELDS.values())]
    pe = fundamentals.get("P/E (trailing)", pd.Series(dtype=float))
    valid_pe = pe[pe > 0]

    portfolio_pe = weighted_average_pe(pe, ctx.weights)
    theme.metric_row(
        (
            ("Portfolio P/E (weighted)", f"{portfolio_pe:.1f}" if portfolio_pe else "–"),
            ("Median holding P/E", f"{valid_pe.median():.1f}" if not valid_pe.empty else "–"),
            ("Holdings with P/E", f"{len(valid_pe)} / {len(pe)}"),
        )
    )
    st.caption(
        "Portfolio P/E is the value-weighted harmonic mean (total value ÷ total "
        "earnings); loss-making holdings with no positive P/E are excluded."
    )

    chart_df = fundamentals[["P/E (trailing)"]].dropna()
    if not chart_df.empty:
        values = chart_df["P/E (trailing)"]
        theme.chart(
            charts.barh(
                chart_df.index,
                values.to_numpy(),
                value_fmt="{:.1f}",
                colors=[charts.ACCENT if v > 0 else charts.LOSS for v in values],
                threshold=portfolio_pe,
                threshold_label=f"Weighted {portfolio_pe:.1f}" if portfolio_pe else None,
                x_title="Trailing P/E",
                height=max(260, 34 * len(chart_df) + 50),
            ),
            alt="Trailing price-to-earnings of each holding, with the portfolio's weighted P/E as a reference",
        )
        st.caption("Red bars are loss-making names, where a trailing P/E is not meaningful.")

    detail = fundamentals.copy()
    if ctx.weights.sum() > 0:
        detail.insert(0, "Weight %", ctx.weights.reindex(detail.index) / ctx.weights.sum() * 100)
    table(
        detail,
        {
            "Weight %": "{:.1f}%",
            "P/E (trailing)": "{:.1f}",
            "P/E (forward)": "{:.1f}",
            "P/B": "{:.2f}",
            "EPS (trailing)": "₹{:,.2f}",
            "Dividend yield (%)": "{:.2f}",
            "Market cap": "₹{:,.0f}",
        },
        alt="Valuation multiples and portfolio weight by holding",
    )


def _render_fundamental_flags(company_data: pd.DataFrame) -> None:
    """The red-flag screen over reported fundamentals."""
    st.subheader("Fundamental flags")
    if company_data.empty:
        st.info("No fundamentals available to screen for red flags.")
        return

    flags = detect_red_flags(company_data)
    if flags.empty:
        st.success("No fundamental red flags detected in the selected holdings.")
        return

    theme.metric_row(
        (
            ("Holdings flagged", f"{flags['Symbol'].nunique()} / {len(company_data)}"),
            ("High severity", flags.loc[flags["Severity"] == "high", "Symbol"].nunique()),
            ("Total flags", len(flags)),
        )
    )
    st.caption(
        "Rule-based screen over reported fundamentals (leverage, earnings, cash "
        "flow, margins, valuation) — prompts to investigate, not verdicts."
    )

    severity_color = {"high": charts.LOSS, "medium": charts.WARN, "low": "#94A3B8"}
    rule_counts = (
        flags.groupby("Flag")
        .agg(Count=("Symbol", "size"), Severity=("Severity", "first"))
        .sort_values("Count", ascending=False)
    )
    theme.chart(
        charts.barh(
            rule_counts.index,
            rule_counts["Count"].to_numpy(),
            value_fmt="{:,.0f}",
            colors=[severity_color.get(s, charts.MUTED) for s in rule_counts["Severity"]],
            x_title="Flags raised",
            height=max(240, 34 * len(rule_counts) + 50),
        ),
        alt="Count of red flags by rule, coloured by severity",
    )
    table(flag_summary(flags), alt="Red-flag counts by holding")
    with st.expander("Every flag, in detail"):
        table(flags, hide_index=True, alt="Red flags detected in each holding")


def _render_default_risk(default_risk: pd.DataFrame, holdings: int) -> None:
    """Altman Z-score zones for the holdings that could be scored."""
    st.subheader("Default risk (Altman Z-score)")
    scored = (
        default_risk.dropna(subset=["Z-score"]) if not default_risk.empty else pd.DataFrame()
    )
    if scored.empty:
        st.info("Not enough statement data to score the holdings.")
        return

    theme.metric_row(
        (
            ("Scored", f"{len(scored)} / {holdings}"),
            ("Distress zone", int((scored["Zone"] == "Distress").sum())),
            ("Grey zone", int((scored["Zone"] == "Grey").sum())),
        )
    )
    st.caption(
        "Altman Z-score — ≥ 2.99 safe, 1.81–2.99 grey, < 1.81 distress. Calibrated "
        "for non-financial corporates, so read lenders and holding companies with "
        "care. A screen, not a probability model."
    )

    zone_color = {"Safe": charts.GAIN, "Grey": charts.WARN, "Distress": charts.LOSS}
    fig = charts.vertical_bar(
        scored.index,
        scored["Z-score"].to_numpy(),
        value_fmt="{:.2f}",
        color=[zone_color.get(z, charts.MUTED) for z in scored["Zone"]],
        y_title="Z-score",
        reference=2.99,
        reference_label="Safe ≥ 2.99",
        height=340,
    )
    fig.add_hline(
        y=1.81,
        line=dict(color=charts.MUTED, width=1.4, dash="dash"),
        annotation_text="Distress < 1.81",
        annotation_position="bottom left",
        annotation_font=dict(size=11, color=charts.MUTED),
    )
    theme.chart(fig, alt="Altman Z-score of each holding with the safe and distress thresholds")
    table(
        scored,
        {
            "Z-score": "{:.2f}",
            "Total assets": "₹{:,.0f}",
            "Total liabilities": "₹{:,.0f}",
            "EBIT": "₹{:,.0f}",
        },
        alt="Altman Z-score by holding",
    )


def _render_surveillance(ctx: AnalyticsContext) -> None:
    """NSE ASM/GSM membership for the holdings."""
    st.subheader("Exchange surveillance (ASM/GSM)")
    surveillance = load_or_empty(load_surveillance, what="NSE surveillance lists")
    if surveillance.empty:
        st.info("Surveillance data is unavailable right now.")
        return

    updated = surveillance["Updated"].dropna()
    if not updated.empty:
        st.caption(f"Lists as of {updated.iloc[0]}.")

    matched = check_symbols(ctx.usable, surveillance)
    if matched.empty:
        st.success("None of your holdings are on NSE's ASM/GSM lists.")
        return

    asm = matched[matched["List"].str.startswith("ASM")]
    gsm = matched[matched["List"] == "GSM"]
    theme.metric_row(
        (
            ("On ASM", asm["Symbol"].nunique()),
            ("On GSM", gsm["Symbol"].nunique()),
            ("Holdings on lists", matched["Symbol"].nunique()),
        )
    )
    table(matched, hide_index=True, alt="Surveillance list memberships by holding")


def render_risk_flags(ctx: AnalyticsContext) -> None:
    """Fundamental flags, default risk and exchange surveillance."""
    company_data = fundamentals_for(ctx)

    market_caps = {}
    if not company_data.empty and "Market cap" in company_data:
        market_caps = company_data["Market cap"].dropna().to_dict()
    default_risk = load_or_empty(
        load_default_risk, ctx.symbols, market_caps, what="default risk"
    )

    _render_fundamental_flags(company_data)
    st.markdown("---")
    _render_default_risk(default_risk, len(ctx.usable))
    st.markdown("---")
    _render_surveillance(ctx)


def render_rebalance(ctx: AnalyticsContext) -> None:
    """Target allocations and the trade list that reaches them."""
    st.caption(
        "Target allocations are built from daily returns; trades are sized against "
        "current market value at the latest close."
    )
    with st.container(horizontal=True, vertical_alignment="bottom"):
        strategy = st.selectbox("Target allocation", STRATEGIES, key="rebalance_strategy")
        max_weight_pct = st.slider(
            "Max weight per holding (%)", 5, 100, 25, 5, key="rebalance_cap"
        )

    latest_prices = ctx.prices.sort_index().ffill().iloc[-1]
    current_values = ctx.filtered_df.groupby("Symbol")["Current Value"].sum().reindex(ctx.usable)
    current_quantities = ctx.filtered_df.groupby("Symbol")["Total Quantity"].sum().reindex(ctx.usable)

    try:
        weights_target = target_weights(ctx.returns, strategy, max_weight_pct / 100)
    except Exception as e:
        st.warning(f"Could not compute a target allocation: {e}")
        weights_target = pd.Series(dtype=float)

    if weights_target.empty:
        st.info("Not enough data to suggest a rebalance.")
        return

    plan = rebalancing_plan(
        current_values, current_quantities, latest_prices, weights_target
    )
    buys = plan[plan["Action"] == "Buy"]
    sells = plan[plan["Action"] == "Sell"]

    theme.metric_row(
        (
            ("Buy value", f"₹{buys['Δ Value'].sum():,.0f}"),
            ("Sell value", f"₹{-sells['Δ Value'].sum():,.0f}"),
            ("Turnover (one-way)", f"{turnover(plan):.1%}"),
        )
    )

    st.subheader("Current versus target allocation")
    comparison = plan[["Current %", "Target %"]].reset_index()
    theme.chart(
        charts.dumbbell(
            comparison["Symbol"],
            comparison["Current %"],
            comparison["Target %"],
            start_name="Current",
            end_name="Target",
            value_fmt="{:.1f}%",
            x_title="Weight",
            height=max(280, 34 * len(comparison) + 60),
        ),
        alt="Current versus target portfolio weight for each holding, joined per holding",
    )
    st.caption(
        "The grey dot is the weight today and the blue dot the target; a longer "
        "connector means a bigger trade."
    )

    table(
        plan,
        {
            "Price": "₹{:,.2f}",
            "Current Qty": "{:,.0f}",
            "Target Qty": "{:,.0f}",
            "Δ Qty": "{:+,.0f}",
            "Current Value": "₹{:,.0f}",
            "Target Value": "₹{:,.0f}",
            "Δ Value": "₹{:+,.0f}",
            "Current %": "{:.1f}%",
            "Target %": "{:.1f}%",
        },
        alt="Rebalancing plan by holding",
    )
    st.caption("Δ Qty is rounded to whole shares; a negative figure is a sell.")


def _render_upcoming_earnings(ctx: AnalyticsContext) -> None:
    """Earnings dates inside the selected horizon."""
    st.subheader("Upcoming earnings")
    earnings = load_or_empty(load_earnings, ctx.symbols, what="the earnings calendar")
    if earnings.empty:
        st.info("No upcoming earnings dates available for the selected holdings.")
        return

    horizon_label = st.segmented_control(
        "Show earnings within",
        ["30 days", "90 days", "6 months"],
        default="90 days",
        key="earnings_horizon",
    ) or "90 days"
    horizon_days = {"30 days": 30, "90 days": 90, "6 months": 182}[horizon_label]
    soon = upcoming(earnings, horizon_days)
    if soon.empty:
        st.info(f"No earnings expected in the next {horizon_label}.")
        return

    theme.chart(
        charts.barh(
            soon["Symbol"],
            soon["Days away"],
            value_fmt="{:,.0f}",
            hover_units=" days away",
            color=charts.ACCENT,
            x_title="Days away",
            height=max(240, 34 * len(soon) + 50),
        ),
        alt="Upcoming earnings by holding, with the number of days until each report",
    )
    table(
        soon,
        {"EPS estimate": "{:,.2f}", "Revenue estimate": "₹{:,.0f}"},
        hide_index=True,
        alt="Upcoming earnings dates for the selected holdings",
    )


def _render_price_forecast(ctx: AnalyticsContext) -> None:
    """Monte Carlo projection of the value-weighted portfolio."""
    st.subheader("Price forecast")
    st.caption(
        "Monte Carlo projection of the value-weighted portfolio from its recent daily "
        "returns — a scenario range, not a prediction. The shaded bands are the 5th–95th "
        "and 25th–75th percentile outcomes; the line is the median."
    )
    with st.container(horizontal=True, vertical_alignment="bottom"):
        horizon_label = st.segmented_control(
            "Forecast horizon",
            ["1 month", "3 months", "6 months"],
            default="3 months",
            key="forecast_horizon",
        ) or "3 months"
        simulations = st.slider("Simulations", 200, 5000, 1000, step=200, key="forecast_sims")
    steps = {"1 month": 21, "3 months": 63, "6 months": 126}[horizon_label]

    start_value = float(ctx.filtered_df["Current Value"].sum())
    projection = forecast_paths(
        ctx.portfolio_returns, start_value, horizon=steps, simulations=simulations
    )
    if projection.empty or start_value <= 0:
        st.info("Not enough return history to build a forecast.")
        return

    last_date = ctx.prices.sort_index().index[-1]
    chart = projection.set_axis(
        [last_date + timedelta(days=round(step * 7 / 5)) for step in projection.index]
    )
    theme.chart(
        charts.fan(
            chart,
            x=chart.index,
            x_title="Projected date",
            y_title="Portfolio value (₹)",
            height=400,
        ),
        alt="Monte Carlo forecast of the portfolio value, showing the 5th to 95th percentile range",
    )

    final = projection.iloc[-1]
    theme.metric_row(
        (
            (
                "Median",
                f"₹{final['P50']:,.0f}",
                f"{(final['P50'] / start_value - 1):+.1%}",
                # The sparkline traces the median path already charted above; the
                # delta colour follows the gain/loss sign.
                {"chart_data": projection["P50"], "delta_description": "vs today"},
            ),
            ("Pessimistic (P5)", f"₹{final['P5']:,.0f}"),
            ("Optimistic (P95)", f"₹{final['P95']:,.0f}"),
        )
    )


def render_outlook(ctx: AnalyticsContext) -> None:
    """The earnings calendar and the price forecast."""
    _render_upcoming_earnings(ctx)
    st.markdown("---")
    _render_price_forecast(ctx)


def _growth_of_one(ctx: AnalyticsContext) -> Optional[pd.DataFrame]:
    """The portfolio's cumulative growth, with the benchmark aligned to it."""
    returns = ctx.portfolio_returns.dropna()
    if len(returns) < 2:
        return None

    growth = (1 + returns).cumprod()
    frame = pd.DataFrame({"Portfolio": growth})

    if ctx.benchmark is not None and not ctx.benchmark.empty:
        benchmark_returns = (
            ctx.benchmark.sort_index()
            .pct_change(fill_method=None)
            .reindex(growth.index)
        )
        benchmark = (1 + benchmark_returns.fillna(0.0)).cumprod()
        if benchmark.iloc[0] != 0:
            benchmark = benchmark / benchmark.iloc[0] * growth.iloc[0]
        frame[BENCHMARK_NAME] = benchmark

    return frame


def render_tearsheet(ctx: AnalyticsContext) -> None:
    """The equity curve, its drawdown and the quantstats metrics table."""
    growth = _growth_of_one(ctx)
    report = full_metrics_report(ctx.portfolio_returns)

    if growth is not None:
        palette = {"Portfolio": charts.ACCENT, BENCHMARK_NAME: charts.MUTED}
        st.subheader("Growth of ₹1")
        theme.chart(
            charts.lines(
                growth,
                colors=palette,
                value_fmt="{:,.3f}",
                y_title="Growth of ₹1",
                fill_first=True,
                height=380,
            ),
            alt="Portfolio growth compared with the benchmark, both starting at one rupee",
        )

        drawdown = growth["Portfolio"] / growth["Portfolio"].cummax() - 1
        st.subheader("Drawdown")
        theme.chart(
            charts.underwater(drawdown, height=260),
            alt="How far the portfolio has fallen from its own previous peak over time",
        )

    if report.empty:
        st.info("Not enough data to build a tearsheet.")
        return

    # quantstats mixes strings and numbers in one column; stringify so Arrow can
    # serialise it for st.dataframe.
    st.subheader("Metrics")
    table(report.astype(str), alt="Portfolio performance metrics (quantstats)")


#: The analytics sections, keyed by the label the segmented control shows and
#: rendered one at a time rather than as ``st.tabs`` — every tab body executes on
#: every rerun, which would force all of the per-symbol network fetches
#: (fundamentals, Z-score statements, earnings) even when the visitor only wants
#: a single view.
SECTIONS: Dict[str, Callable[[AnalyticsContext], None]] = {
    "Correlation": render_correlation,
    "Beta & Risk": render_beta,
    "Valuation": render_valuation,
    "Risk Flags": render_risk_flags,
    "Rebalance": render_rebalance,
    "Outlook": render_outlook,
    "Tearsheet": render_tearsheet,
}
ANALYTICS_SECTIONS: Tuple[str, ...] = tuple(SECTIONS)


@st.fragment
def analytics_section(ctx: AnalyticsContext) -> None:
    """The section switcher and the selected renderer, as one fragment.

    Switching sections then reruns only this block instead of the whole page,
    so the distribution charts and headline metrics above are not rebuilt for a
    view they do not affect.
    """
    section = st.segmented_control(
        "Analytics section",
        ANALYTICS_SECTIONS,
        default=ANALYTICS_SECTIONS[0],
        key="analytics_section",
        label_visibility="collapsed",
    )
    # The control can be cleared back to no selection.
    SECTIONS[section or ANALYTICS_SECTIONS[0]](ctx)


def render_analytics(filtered_df: pd.DataFrame, symbols: list) -> None:
    """Render correlation, beta and quantstats-based portfolio analytics."""
    st.markdown("---")
    st.subheader("Portfolio analytics")
    st.caption(
        f"Daily prices via Yahoo Finance · benchmark {BENCHMARK_NAME} · "
        "metrics computed on value-weighted daily returns."
    )

    if not symbols:
        st.info("Select at least one symbol to see analytics.")
        return

    period = st.segmented_control(
        "Lookback period",
        ["6mo", "1y", "2y", "5y"],
        default="1y",
        key="analytics_period",
    ) or "1y"

    try:
        prices, benchmark = load_price_history(tuple(sorted(symbols)), period)
    except Exception as e:  # network / parsing failures should not break the page
        st.warning(f"Could not fetch market data: {e}")
        return

    if prices is None or prices.empty:
        st.info("No market data available for the selected symbols.")
        return

    missing = sorted(s for s in symbols if s not in prices.columns)
    if missing:
        st.caption("No market data for: " + ", ".join(missing))

    returns = compute_returns(prices)
    if returns.empty or len(returns) < MIN_OBSERVATIONS:
        st.info("Not enough price history to compute reliable analytics.")
        return

    usable = [c for c in returns.columns if returns[c].notna().sum() >= MIN_OBSERVATIONS]
    skipped = sorted(c for c in returns.columns if c not in usable)
    if skipped:
        st.caption("Skipped (insufficient history): " + ", ".join(skipped))
    if not usable:
        st.info("No symbol had enough overlapping price history.")
        return

    returns = returns[usable]
    weights = filtered_df.groupby("Symbol")["Invested Value"].sum()
    ctx = AnalyticsContext(
        filtered_df=filtered_df,
        usable=usable,
        returns=returns,
        weights=weights,
        portfolio_returns=weighted_portfolio_returns(returns, weights),
        prices=prices,
        benchmark=benchmark,
    )

    analytics_section(ctx)


def choose_portfolio() -> pd.DataFrame:
    """The portfolio to analyse: a saved client, this session's import, or the sample.

    The picker lives in the sidebar because choosing a client frames everything
    on the page. The session's import is offered alongside the saved clients so a
    freshly imported file is analysable without being saved first.
    """
    saved = portfolio_store.list_saved()
    session = portfolio_store.get_active()
    session_label = portfolio_store.active_label()
    options = portfolio_store.book_options(saved, session_label)
    default = session_label if session_label in options else "Sample portfolio"
    choice = st.sidebar.selectbox(
        "Portfolio", options, index=options.index(default), key="portfolio_choice"
    )

    if choice == "Sample portfolio":
        st.info(
            "Showing the **sample portfolio**. Bring your own from the "
            "**Import Portfolio** page."
        )
        return load_sample_holdings()

    if session is not None and choice == session_label:
        frame = session
    else:
        frame = portfolio_store.load_saved(choice)
    if frame is None:
        st.warning(f"Could not read **{choice}**; showing the sample instead.")
        return load_sample_holdings()

    st.caption(f"Viewing **{choice}** — {len(frame)} holdings.")
    return holdings.to_core(frame)


def main():
    theme.page_header(
        "Co-Pilot · Portfolio Management",
        "P&L, risk, red flags and a rebalancing plan for your holdings.",
    )
    # How to Use Section
    with st.expander("How to use this"):
        st.markdown(Path("HOW_TO_USE.md").read_text())

    # The client book: pick a saved client, the session's import, or the sample.
    df = choose_portfolio()

    sectors_data = load_sectors()

    # Symbol Selection in Sidebar
    symbols = st.sidebar.multiselect(
        "Select symbols",
        options=sorted(df["Symbol"].unique()),
        default=df["Symbol"].unique()
    )

    # Filter and merge data
    filtered_df = df.loc[df["Symbol"].isin(symbols)]
    df_with_sectors = pd.merge(
        filtered_df,
        sectors_data,
        on='Symbol',
        how='left'
    )

    # Display Metrics
    total_investment = filtered_df['Invested Value'].sum()
    current_value = filtered_df['Current Value'].sum()
    pnl = current_value - total_investment
    pct_change = (pnl / total_investment) * 100 if total_investment else 0

    theme.metric_row(
        (
            ('Total investment', f"₹{total_investment:,.0f}"),
            ('Current value', f"₹{current_value:,.0f}"),
            (
                'Total P&L',
                f"₹{pnl:,.0f}",
                # A flat move must not show a green up-arrow (see st.metric).
                0 if round(pct_change, 1) == 0 else f"{pct_change:+.1f}%",
                {"delta_description": "vs invested"},
            ),
        )
    )

    # Display Holdings
    with st.expander("Holdings details"):
        st.dataframe(
            filtered_df,
            hide_index=True,
            alt="Holdings with quantities and invested and current value",
            column_config={
                "Total Quantity": st.column_config.NumberColumn(
                    "Quantity", format="%,.0f"
                ),
                "Invested Value": st.column_config.NumberColumn(format="₹%,.0f"),
                "Current Value": st.column_config.NumberColumn(format="₹%,.0f"),
            },
        )

    # Distribution and P&L, then the deeper analytics.
    if filtered_df.empty:
        st.info("Select at least one symbol to see the portfolio breakdown.")
    else:
        render_allocation(filtered_df, df_with_sectors)

    render_analytics(filtered_df, list(symbols))


if __name__ == "__main__":
    main()
