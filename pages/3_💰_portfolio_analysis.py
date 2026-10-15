import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
from datetime import timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
from plotly.graph_objs._figure import Figure

from utils.rebalancing import (
    STRATEGIES,
    rebalancing_plan,
    target_weights,
    turnover,
)
from utils.default_risk import fetch_default_risk
from utils.earnings import fetch_earnings_calendar, upcoming
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
    fetch_company_data,
    fetch_price_history,
    full_metrics_report,
    performance_summary,
    weighted_average_pe,
    weighted_portfolio_returns,
)
from utils.red_flags import detect_red_flags, flag_summary
from utils.surveillance import check_symbols, fetch_surveillance

# Constants
QUANTITY_COLUMNS = ['Quantity Available', 'Quantity Discrepant', 'Quantity Long Term', 
                   'Quantity Pledged (Margin)', 'Quantity Pledged (Loan)']
REQUIRED_COLUMNS = ['Symbol', 'Average Price', 'Previous Closing Price'] + QUANTITY_COLUMNS

# Analytics sections. They are rendered one at a time rather than as ``st.tabs``,
# because every tab body executes on every rerun — which would trigger all of the
# per-symbol network fetches even when the visitor only opens one section.
ANALYTICS_SECTIONS = (
    "🔗 Correlation",
    "🎯 Beta & Risk",
    "💹 Valuation",
    "🚩 Risk Flags",
    "⚖️ Rebalance",
    "🔮 Outlook",
    "📈 Tearsheet",
)

@st.cache_data(ttl=3600)
def load_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load and cache both portfolio and sector data"""
    portfolio = pd.read_excel('./data/holdings-sample.xlsx', header=22, usecols="B:L")
    sectors = pd.read_csv('./data/stock-sector.csv').rename(columns={"NSE code": "Symbol"})
    return portfolio, sectors

@st.cache_data(ttl=3600, show_spinner="Fetching market data…")
def load_price_history(symbols: Tuple[str, ...], period: str) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Fetch and cache daily price history for the given symbols."""
    return fetch_price_history(symbols, period=period)

@st.cache_data(ttl=3600, show_spinner="Fetching fundamentals…")
def load_company_data(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Fetch and cache fundamentals (valuation + risk) for the given symbols."""
    return fetch_company_data(symbols, COMPANY_FIELDS)

@st.cache_data(ttl=21600, show_spinner="Fetching NSE surveillance lists…")
def load_surveillance() -> pd.DataFrame:
    """Fetch and cache the NSE ASM/GSM surveillance lists (refreshed daily)."""
    return fetch_surveillance()

@st.cache_data(ttl=21600, show_spinner="Crunching company statements…")
def load_default_risk(symbols: Tuple[str, ...], market_caps: Dict[str, float]) -> pd.DataFrame:
    """Fetch statements and compute Altman Z-scores for the given symbols."""
    return fetch_default_risk(symbols, pd.Series(market_caps))

@st.cache_data(ttl=3600, show_spinner="Fetching earnings calendar…")
def load_earnings(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Fetch and cache upcoming earnings dates for the given symbols."""
    return fetch_earnings_calendar(symbols)

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

def render_analytics(filtered_df: pd.DataFrame, symbols: list) -> None:
    """Render correlation, beta and quantstats-based portfolio analytics."""
    st.markdown("---")
    st.subheader("📊 Portfolio Analytics")
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
        st.caption("⚠️ No market data for: " + ", ".join(missing))

    returns = compute_returns(prices)
    if returns.empty or len(returns) < MIN_OBSERVATIONS:
        st.info("Not enough price history to compute reliable analytics.")
        return

    usable = [c for c in returns.columns if returns[c].notna().sum() >= MIN_OBSERVATIONS]
    skipped = sorted(c for c in returns.columns if c not in usable)
    if skipped:
        st.caption("⚠️ Skipped (insufficient history): " + ", ".join(skipped))
    if not usable:
        st.info("No symbol had enough overlapping price history.")
        return

    returns = returns[usable]
    weights = filtered_df.groupby("Symbol")["Invested Value"].sum()
    portfolio_returns = weighted_portfolio_returns(returns, weights)

    # Render one section at a time. ``st.tabs`` executes every body on every
    # rerun, which would force all of the per-symbol network fetches
    # (fundamentals, Z-score statements, earnings) even when the visitor only
    # wants a single view.
    section = st.segmented_control(
        "Analytics section",
        ANALYTICS_SECTIONS,
        default=ANALYTICS_SECTIONS[0],
        key="analytics_section",
        label_visibility="collapsed",
    )
    if section is None:  # the control can be cleared back to no selection
        section = ANALYTICS_SECTIONS[0]

    if section == "🔗 Correlation":
        corr = correlation_matrix(returns)
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

    if section == "🎯 Beta & Risk":
        if benchmark is not None and not benchmark.empty:
            beta = compute_beta(returns, benchmark)
            if beta.empty:
                st.info("Not enough overlap with the benchmark to compute beta.")
            else:
                st.dataframe(beta.to_frame().style.format("{:.2f}"), width="stretch")
                st.caption(
                    f"Beta vs {BENCHMARK_NAME}: above 1 moves more than the index, "
                    "below 1 moves less."
                )
        else:
            st.info(f"{BENCHMARK_NAME} history unavailable; beta cannot be computed.")

        st.markdown("**Value-weighted portfolio risk / return**")
        st.dataframe(
            format_summary(performance_summary(portfolio_returns)).to_frame(),
            width="stretch",
        )

    if section == "💹 Valuation":
        try:
            company_data = load_company_data(tuple(sorted(usable)))
        except Exception as e:  # network / parsing failures should not break the page
            st.warning(f"Could not fetch fundamentals: {e}")
            company_data = pd.DataFrame()

        if company_data is None or company_data.empty:
            st.info("No valuation data available for the selected symbols.")
        else:
            fundamentals = company_data[list(FUNDAMENTAL_FIELDS.values())]
            pe = fundamentals.get("P/E (trailing)", pd.Series(dtype=float))
            valid_pe = pe[pe > 0]

            c1, c2, c3 = st.columns(3)
            portfolio_pe = weighted_average_pe(pe, weights)
            c1.metric("Portfolio P/E (weighted)", f"{portfolio_pe:.1f}" if portfolio_pe else "–")
            c2.metric("Median holding P/E", f"{valid_pe.median():.1f}" if not valid_pe.empty else "–")
            c3.metric("Holdings with P/E", f"{len(valid_pe)} / {len(pe)}")
            st.caption(
                "Portfolio P/E is the value-weighted harmonic mean (total value ÷ total "
                "earnings); loss-making holdings with no positive P/E are excluded."
            )

            table = fundamentals.copy()
            if weights.sum() > 0:
                table.insert(0, "Weight %", weights.reindex(table.index) / weights.sum() * 100)
            st.dataframe(
                table.style.format(
                    {
                        "Weight %": "{:.1f}%",
                        "P/E (trailing)": "{:.1f}",
                        "P/E (forward)": "{:.1f}",
                        "P/B": "{:.2f}",
                        "EPS (trailing)": "₹{:,.2f}",
                        "Dividend yield (%)": "{:.2f}",
                        "Market cap": "₹{:,.0f}",
                    },
                    na_rep="–",
                ),
                width="stretch",
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

    if section == "🚩 Risk Flags":
        try:
            company_data = load_company_data(tuple(sorted(usable)))
        except Exception as e:  # network / parsing failures should not break the page
            st.warning(f"Could not fetch fundamentals: {e}")
            company_data = pd.DataFrame()

        market_caps = {}
        if company_data is not None and not company_data.empty and "Market cap" in company_data:
            market_caps = company_data["Market cap"].dropna().to_dict()

        try:
            default_risk = load_default_risk(tuple(sorted(usable)), market_caps)
        except Exception as e:
            st.warning(f"Could not assess default risk: {e}")
            default_risk = pd.DataFrame()

        st.subheader("Fundamental flags")
        if company_data is None or company_data.empty:
            st.info("No fundamentals available to screen for red flags.")
        else:
            flags = detect_red_flags(company_data)
            if flags.empty:
                st.success("✅ No fundamental red flags detected in the selected holdings.")
            else:
                flagged = flags["Symbol"].nunique()
                high = flags.loc[flags["Severity"] == "high", "Symbol"].nunique()
                c1, c2, c3 = st.columns(3)
                c1.metric("Holdings flagged", f"{flagged} / {len(company_data)}")
                c2.metric("High severity", high)
                c3.metric("Total flags", len(flags))
                st.caption(
                    "Rule-based screen over reported fundamentals (leverage, earnings, cash "
                    "flow, margins, valuation) — prompts to investigate, not verdicts."
                )
                st.dataframe(flag_summary(flags), width="stretch")
                st.dataframe(flags, width="stretch", hide_index=True)

        st.markdown("---")
        st.subheader("Default risk (Altman Z-score)")
        scored = pd.DataFrame()
        if default_risk is not None and not default_risk.empty:
            scored = default_risk.dropna(subset=["Z-score"])
        if scored.empty:
            st.info("Not enough statement data to score the holdings.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Scored", f"{len(scored)} / {len(usable)}")
            c2.metric("Distress zone", int((scored["Zone"] == "Distress").sum()))
            c3.metric("Grey zone", int((scored["Zone"] == "Grey").sum()))
            st.caption(
                "Altman Z-score — ≥ 2.99 safe, 1.81–2.99 grey, < 1.81 distress. Calibrated "
                "for non-financial corporates, so read lenders and holding companies with "
                "care. A screen, not a probability model."
            )
            st.dataframe(
                scored.style.format(
                    {
                        "Z-score": "{:.2f}",
                        "Total assets": "₹{:,.0f}",
                        "Total liabilities": "₹{:,.0f}",
                        "EBIT": "₹{:,.0f}",
                    },
                    na_rep="–",
                ),
                width="stretch",
            )

        st.markdown("---")
        st.subheader("Exchange surveillance (ASM/GSM)")
        try:
            surveillance = load_surveillance()
        except Exception as e:
            st.warning(f"Could not fetch NSE surveillance lists: {e}")
            surveillance = pd.DataFrame()

        if surveillance is None or surveillance.empty:
            st.info("Surveillance data is unavailable right now.")
        else:
            updated = surveillance["Updated"].dropna()
            if not updated.empty:
                st.caption(f"Lists as of {updated.iloc[0]}.")

            matched = check_symbols(usable, surveillance)
            if matched.empty:
                st.success("✅ None of your holdings are on NSE's ASM/GSM lists.")
            else:
                asm = matched[matched["List"].str.startswith("ASM")]
                gsm = matched[matched["List"] == "GSM"]
                c1, c2, c3 = st.columns(3)
                c1.metric("On ASM", asm["Symbol"].nunique())
                c2.metric("On GSM", gsm["Symbol"].nunique())
                c3.metric("Holdings on lists", matched["Symbol"].nunique())
                st.dataframe(matched, width="stretch", hide_index=True)

    if section == "⚖️ Rebalance":
        st.caption(
            "Target allocations are built from daily returns; trades are sized against "
            "current market value at the latest close."
        )
        c1, c2 = st.columns(2)
        strategy = c1.selectbox("Target allocation", STRATEGIES, key="rebalance_strategy")
        max_weight_pct = c2.slider(
            "Max weight per holding (%)", 5, 100, 25, 5, key="rebalance_cap"
        )

        latest_prices = prices.sort_index().ffill().iloc[-1]
        current_values = filtered_df.groupby("Symbol")["Current Value"].sum().reindex(usable)
        current_quantities = filtered_df.groupby("Symbol")["Total Quantity"].sum().reindex(usable)

        try:
            weights_target = target_weights(returns, strategy, max_weight_pct / 100)
        except Exception as e:
            st.warning(f"Could not compute a target allocation: {e}")
            weights_target = pd.Series(dtype=float)

        if weights_target.empty:
            st.info("Not enough data to suggest a rebalance.")
        else:
            plan = rebalancing_plan(
                current_values, current_quantities, latest_prices, weights_target
            )
            buys = plan[plan["Action"] == "Buy"]
            sells = plan[plan["Action"] == "Sell"]

            m1, m2, m3 = st.columns(3)
            m1.metric("Buy value", f"₹{buys['Δ Value'].sum():,.0f}")
            m2.metric("Sell value", f"₹{-sells['Δ Value'].sum():,.0f}")
            m3.metric("Turnover (one-way)", f"{turnover(plan):.1%}")

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

            st.dataframe(
                plan.style.format(
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
                    na_rep="–",
                ),
                width="stretch",
            )
            st.caption("Δ Qty is rounded to whole shares; a negative figure is a sell.")

    if section == "🔮 Outlook":
        try:
            earnings = load_earnings(tuple(sorted(usable)))
        except Exception as e:
            st.warning(f"Could not fetch the earnings calendar: {e}")
            earnings = pd.DataFrame()

        st.subheader("Upcoming earnings")
        if earnings is None or earnings.empty:
            st.info("No upcoming earnings dates available for the selected holdings.")
        else:
            horizon_label = st.selectbox(
                "Show earnings within", ["30 days", "90 days", "6 months"], index=1,
                key="earnings_horizon",
            )
            horizon_days = {"30 days": 30, "90 days": 90, "6 months": 182}[horizon_label]
            soon = upcoming(earnings, horizon_days)
            if soon.empty:
                st.info(f"No earnings expected in the next {horizon_label}.")
            else:
                st.dataframe(
                    soon.style.format(
                        {"EPS estimate": "{:,.2f}", "Revenue estimate": "₹{:,.0f}"}, na_rep="–"
                    ),
                    width="stretch",
                    hide_index=True,
                )

        st.markdown("---")
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

        start_value = float(filtered_df["Current Value"].sum())
        projection = forecast_paths(portfolio_returns, start_value, horizon=steps, simulations=simulations)
        if projection.empty or start_value <= 0:
            st.info("Not enough return history to build a forecast.")
        else:
            last_date = prices.sort_index().index[-1]
            chart = projection.set_axis(
                [last_date + timedelta(days=round(step * 7 / 5)) for step in projection.index]
            )
            fig = px.line(chart, template="plotly_white")
            for trace in fig.data:
                if trace.name == "P50":
                    trace.update(line=dict(width=3, color="#226216"))
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
            c1, c2, c3 = st.columns(3)
            c1.metric("Median", f"₹{final['P50']:,.0f}", f"{(final['P50'] / start_value - 1):+.1%}")
            c2.metric("Pessimistic (P5)", f"₹{final['P5']:,.0f}")
            c3.metric("Optimistic (P95)", f"₹{final['P95']:,.0f}")

    if section == "📈 Tearsheet":
        report = full_metrics_report(portfolio_returns)
        if report.empty:
            st.info("Not enough data to build a tearsheet.")
        else:
            # quantstats mixes strings and numbers in one column; stringify so
            # Arrow can serialise it for st.dataframe.
            st.dataframe(report.astype(str), width="stretch")

def main():
    st.set_page_config("Co-Pilot (Portfolio Management)", "🚀", layout="wide")
    st.title("🚀 Co-Pilot (Portfolio Management)")
    # How to Use Section
    with st.expander("ℹ️ How to Use This"):
        st.markdown(Path("HOW_TO_USE.md").read_text())
        # File Upload with Zerodha Instructions
        st.markdown("### 📂 Upload Holdings")
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
                st.success("✅ Successfully loaded your portfolio!")
            else:
                st.error("❌ Invalid file format. Using sample data instead.")
        except Exception as e:
            st.error(f"❌ Error loading file: {e}")
            st.info("ℹ️ Using sample data for demonstration")
    else:
        st.info("ℹ️ Currently showing sample portfolio data. Upload your holdings file to see your actual portfolio.")

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
    
    c1, c2, c3 = st.columns(3)
    c1.metric('Total Investment', f"₹{total_investment:,.0f}")
    c2.metric('Current Value', f"₹{current_value:,.0f}")
    c3.metric('Total P&L', f"₹{pnl:,.0f}", f"{pct_change:+.1f}%")
    
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
