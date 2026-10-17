import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple
from plotly.graph_objs._figure import Figure

from utils import snapshot, theme
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

# Constants
QUANTITY_COLUMNS = ['Quantity Available', 'Quantity Discrepant', 'Quantity Long Term', 
                   'Quantity Pledged (Margin)', 'Quantity Pledged (Loan)']
REQUIRED_COLUMNS = ['Symbol', 'Average Price', 'Previous Closing Price'] + QUANTITY_COLUMNS

@st.cache_data(ttl=3600)
def load_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load and cache both portfolio and sector data"""
    portfolio = pd.read_excel('./data/holdings-sample.xlsx', header=22, usecols="B:L")
    sectors = pd.read_csv('./data/stock-sector.csv').rename(columns={"NSE code": "Symbol"})
    return portfolio, sectors

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

@st.cache_data(ttl=3600, show_spinner="Fetching market data…")
def load_price_history(symbols: Tuple[str, ...], period: str) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Daily price history, served from the nightly snapshot where possible."""
    return snapshot.load_prices(symbols, period=period, store=snapshot_store())

@st.cache_data(ttl=3600, show_spinner="Fetching fundamentals…")
def load_company_data(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Fundamentals (valuation + risk), served from the snapshot where possible."""
    return snapshot.load_company_data(symbols, COMPANY_FIELDS, store=snapshot_store())

@st.cache_data(ttl=21600, show_spinner="Fetching NSE surveillance lists…")
def load_surveillance() -> pd.DataFrame:
    """NSE ASM/GSM surveillance lists (refreshed daily)."""
    return snapshot.load_surveillance(store=snapshot_store())

@st.cache_data(ttl=21600, show_spinner="Crunching company statements…")
def load_default_risk(symbols: Tuple[str, ...], market_caps: Dict[str, float]) -> pd.DataFrame:
    """Altman Z-scores for the given symbols, snapshot-first."""
    return snapshot.load_default_risk(
        symbols, pd.Series(market_caps), store=snapshot_store()
    )

@st.cache_data(ttl=3600, show_spinner="Fetching earnings calendar…")
def load_earnings(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Upcoming earnings dates for the given symbols, snapshot-first."""
    return snapshot.load_earnings(symbols, store=snapshot_store())

def process_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    """Process portfolio data efficiently"""
    df = df.copy()
    df['Total Quantity'] = df.loc[:, QUANTITY_COLUMNS].sum(axis='columns')
    df['Invested Value'] = df['Total Quantity'] * df['Average Price']
    df['Current Value'] = df['Total Quantity'] * df['Previous Closing Price']
    return df[['Symbol', 'Total Quantity', 'Invested Value', 'Current Value']]

def create_charts(df: pd.DataFrame, df_with_sectors: pd.DataFrame) -> Tuple[Figure, Figure]:
    """Create portfolio charts"""
    symbol_fig = px.pie(df, values="Invested Value", names="Symbol", template="plotly_white")
    sector_fig = px.pie(df_with_sectors, values="Invested Value", names="Sector", template="plotly_white")
    
    for fig in [symbol_fig, sector_fig]:
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        fig.update_traces(textposition='inside', textinfo='percent+label')
    
    return symbol_fig, sector_fig

def format_summary(summary: pd.Series) -> pd.Series:
    """Format a numeric performance summary for display."""
    formatted: Dict[str, str] = {}
    for label, value in summary.items():
        if pd.isna(value):
            formatted[label] = "–"
        elif label in PERCENT_METRICS:
            formatted[label] = f"{value:.2%}"
        else:
            formatted[label] = f"{value:.2f}"
    return pd.Series(formatted, name="Portfolio")


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
) -> None:
    """Render a dataframe, applying ``formats`` when given.

    ``formats`` is either one format string for every column or a mapping of
    column to format string; missing values always show as an en dash.
    """
    st.dataframe(
        data.style.format(formats, na_rep="–") if formats is not None else data,
        width="stretch",
        hide_index=hide_index,
    )


def render_correlation(ctx: AnalyticsContext) -> None:
    """Correlation heatmap of the holdings' daily returns."""
    corr = correlation_matrix(ctx.returns)
    fig = px.imshow(
        corr,
        text_auto=".2f",
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu_r",
        aspect="auto",
        template="plotly_white",
    )
    fig.update_layout(margin=dict(t=10, b=0, l=0, r=0))
    st.plotly_chart(fig, width="stretch")

    if len(corr) > 1:
        upper = np.triu(np.ones(corr.shape), k=1).astype(bool)
        pairs = corr.where(upper).stack().sort_values(ascending=False)
        st.caption(
            "Most correlated pairs: "
            + ", ".join(f"{a} / {b} ({v:.2f})" for (a, b), v in pairs.head(3).items())
        )


def render_beta(ctx: AnalyticsContext) -> None:
    """Per-holding beta against the benchmark plus the portfolio risk/return."""
    if ctx.benchmark is not None and not ctx.benchmark.empty:
        beta = compute_beta(ctx.returns, ctx.benchmark)
        if beta.empty:
            st.info("Not enough overlap with the benchmark to compute beta.")
        else:
            table(beta.to_frame(), "{:.2f}")
            st.caption(
                f"Beta vs {BENCHMARK_NAME}: above 1 moves more than the index, "
                "below 1 moves less."
            )
    else:
        st.info(f"{BENCHMARK_NAME} history unavailable; beta cannot be computed.")

    st.markdown("**Value-weighted portfolio risk / return**")
    table(format_summary(performance_summary(ctx.portfolio_returns)).to_frame())


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
    )

    chart_df = fundamentals.reset_index()
    chart_df = chart_df[chart_df["P/E (trailing)"].notna()]
    if not chart_df.empty:
        fig = px.bar(
            chart_df,
            x="Symbol",
            y="P/E (trailing)",
            template="plotly_white",
            title="Trailing P/E by holding",
        )
        fig.update_layout(margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig, width="stretch")


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
    table(flag_summary(flags))
    table(flags, hide_index=True)


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
    table(
        scored,
        {
            "Z-score": "{:.2f}",
            "Total assets": "₹{:,.0f}",
            "Total liabilities": "₹{:,.0f}",
            "EBIT": "₹{:,.0f}",
        },
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
    table(matched, hide_index=True)


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
    c1, c2 = st.columns(2)
    strategy = c1.selectbox("Target allocation", STRATEGIES, key="rebalance_strategy")
    max_weight_pct = c2.slider(
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

    comparison = plan[["Current %", "Target %"]].reset_index()
    fig = px.bar(
        comparison,
        x="Symbol",
        y=["Current %", "Target %"],
        barmode="group",
        template="plotly_white",
        title="Current vs target allocation",
    )
    fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), xaxis_title="", yaxis_title="%")
    st.plotly_chart(fig, width="stretch")

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
    )
    st.caption("Δ Qty is rounded to whole shares; a negative figure is a sell.")


def _render_upcoming_earnings(ctx: AnalyticsContext) -> None:
    """Earnings dates inside the selected horizon."""
    st.subheader("Upcoming earnings")
    earnings = load_or_empty(load_earnings, ctx.symbols, what="the earnings calendar")
    if earnings.empty:
        st.info("No upcoming earnings dates available for the selected holdings.")
        return

    horizon_label = st.selectbox(
        "Show earnings within", ["30 days", "90 days", "6 months"], index=1,
        key="earnings_horizon",
    )
    horizon_days = {"30 days": 30, "90 days": 90, "6 months": 182}[horizon_label]
    soon = upcoming(earnings, horizon_days)
    if soon.empty:
        st.info(f"No earnings expected in the next {horizon_label}.")
        return

    table(
        soon,
        {"EPS estimate": "{:,.2f}", "Revenue estimate": "₹{:,.0f}"},
        hide_index=True,
    )


def _render_price_forecast(ctx: AnalyticsContext) -> None:
    """Monte Carlo projection of the value-weighted portfolio."""
    st.subheader("Price forecast")
    st.caption(
        "Monte Carlo projection of the value-weighted portfolio from its recent daily "
        "returns — a scenario range, not a prediction."
    )
    c1, c2 = st.columns(2)
    horizon_label = c1.selectbox(
        "Forecast horizon", ["1 month", "3 months", "6 months"], index=1, key="forecast_horizon"
    )
    simulations = c2.slider("Simulations", 200, 5000, 1000, step=200, key="forecast_sims")
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
    fig = px.line(chart, template="plotly_white")
    for trace in fig.data:
        if trace.name == "P50":
            trace.update(line=dict(width=3, color=theme.ACCENT))
        else:
            trace.update(line=dict(width=1, dash="dot"))
    fig.update_layout(
        margin=dict(t=20, b=0, l=0, r=0),
        xaxis_title="Projected date",
        yaxis_title="Portfolio value (₹)",
        legend_title="Percentile",
    )
    st.plotly_chart(fig, width="stretch")

    final = projection.iloc[-1]
    theme.metric_row(
        (
            ("Median", f"₹{final['P50']:,.0f}", f"{(final['P50'] / start_value - 1):+.1%}"),
            ("Pessimistic (P5)", f"₹{final['P5']:,.0f}"),
            ("Optimistic (P95)", f"₹{final['P95']:,.0f}"),
        )
    )


def render_outlook(ctx: AnalyticsContext) -> None:
    """The earnings calendar and the price forecast."""
    _render_upcoming_earnings(ctx)
    st.markdown("---")
    _render_price_forecast(ctx)


def render_tearsheet(ctx: AnalyticsContext) -> None:
    """The full quantstats metrics table."""
    report = full_metrics_report(ctx.portfolio_returns)
    if report.empty:
        st.info("Not enough data to build a tearsheet.")
        return

    # quantstats mixes strings and numbers in one column; stringify so Arrow can
    # serialise it for st.dataframe.
    table(report.astype(str))


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


def render_analytics(filtered_df: pd.DataFrame, symbols: list) -> None:
    """Render correlation, beta and quantstats-based portfolio analytics."""
    st.markdown("---")
    st.subheader("Portfolio Analytics")
    st.caption(
        f"Daily prices via Yahoo Finance · benchmark {BENCHMARK_NAME} · "
        "metrics computed on value-weighted daily returns."
    )

    if not symbols:
        st.info("Select at least one symbol to see analytics.")
        return

    period = st.selectbox("Lookback period", ["6mo", "1y", "2y", "5y"], index=1)

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

    section = st.segmented_control(
        "Analytics section",
        ANALYTICS_SECTIONS,
        default=ANALYTICS_SECTIONS[0],
        key="analytics_section",
        label_visibility="collapsed",
    )
    # The control can be cleared back to no selection.
    SECTIONS[section or ANALYTICS_SECTIONS[0]](ctx)


def main():
    theme.page_header(
        "Co-Pilot · Portfolio Management",
        "Upload your Zerodha holdings for P&L, risk, red flags and a rebalancing plan.",
    )
    # How to Use Section
    with st.expander("How to Use This"):
        st.markdown(Path("HOW_TO_USE.md").read_text())
        # File Upload with Zerodha Instructions
        st.markdown("### Upload Holdings")
        st.markdown("""
            Upload your holdings from Zerodha:
            - [Family Portfolio](https://console.zerodha.com/portfolio/holdings/family)
            - [Personal Portfolio](https://console.zerodha.com/portfolio/holdings/)
        """)
    
    # Initialize session state
    if 'data_loaded' not in st.session_state:
        st.session_state.portfolio_data, st.session_state.sectors_data = load_data()
        st.session_state.data_loaded = True
    
    
    uploaded_file = st.file_uploader(
        "Drop your holdings Excel file here",
        type=['xlsx'],
        help="Export and upload your holdings data from Zerodha Console"
    )

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, header=22, usecols="B:L")
            if set(REQUIRED_COLUMNS).issubset(df.columns):
                st.session_state.portfolio_data = df
                st.success("Successfully loaded your portfolio!")
            else:
                st.error("Invalid file format. Using sample data instead.")
        except Exception as e:
            st.error(f"Error loading file: {e}")
            st.info("Using sample data for demonstration")
    else:
        st.info("Currently showing sample portfolio data. Upload your holdings file to see your actual portfolio.")

    # Process Data
    df = process_portfolio(st.session_state.portfolio_data)
    
    # Symbol Selection in Sidebar
    symbols = st.sidebar.multiselect(
        "Select Symbols",
        options=sorted(df["Symbol"].unique()),
        default=df["Symbol"].unique()
    )
    
    # Filter and merge data
    filtered_df = df.loc[df["Symbol"].isin(symbols)]
    df_with_sectors = pd.merge(
        filtered_df,
        st.session_state.sectors_data,
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
            ('Total Investment', f"₹{total_investment:,.0f}"),
            ('Current Value', f"₹{current_value:,.0f}"),
            ('Total P&L', f"₹{pnl:,.0f}", f"{pct_change:+.1f}%"),
        )
    )
    
    # Display Holdings
    with st.expander("Holdings Details"):
        st.dataframe(
            filtered_df.style.format({
                'Invested Value': '₹{:,.0f}',
                'Current Value': '₹{:,.0f}',
                'Total Quantity': '{:,.0f}'
            }),
            width="stretch",
            hide_index=True
        )
    
    # Display Charts
    c1, c2 = st.columns(2)
    symbol_fig, sector_fig = create_charts(filtered_df, df_with_sectors)
    
    c1.subheader("Investment Distribution")
    c1.plotly_chart(symbol_fig, width="stretch")
    
    c2.subheader("Sector Distribution")
    c2.plotly_chart(sector_fig, width="stretch")

    # Analytics (correlation, beta, quantstats)
    render_analytics(filtered_df, list(symbols))

if __name__ == "__main__":
    main()
