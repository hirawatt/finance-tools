import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
from pathlib import Path
from typing import Dict, Optional, Tuple
from plotly.graph_objs._figure import Figure

from utils.rebalancing import (
    STRATEGIES,
    rebalancing_plan,
    target_weights,
    turnover,
)
from utils.market_data import (
    BENCHMARK_NAME,
    MIN_OBSERVATIONS,
    PERCENT_METRICS,
    compute_beta,
    compute_returns,
    correlation_matrix,
    fetch_fundamentals,
    fetch_price_history,
    full_metrics_report,
    performance_summary,
    weighted_average_pe,
    weighted_portfolio_returns,
)

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

@st.cache_data(ttl=3600, show_spinner="Fetching market data…")
def load_price_history(symbols: Tuple[str, ...], period: str) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """Fetch and cache daily price history for the given symbols."""
    return fetch_price_history(symbols, period=period)

@st.cache_data(ttl=3600, show_spinner="Fetching valuation data…")
def load_fundamentals(symbols: Tuple[str, ...]) -> pd.DataFrame:
    """Fetch and cache valuation fundamentals for the given symbols."""
    return fetch_fundamentals(symbols)

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

    corr_tab, risk_tab, valuation_tab, rebalance_tab, tearsheet_tab = st.tabs(
        ["🔗 Correlation", "🎯 Beta & Risk", "💹 Valuation", "⚖️ Rebalance", "📈 Tearsheet"]
    )

    with corr_tab:
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

    with risk_tab:
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

    with valuation_tab:
        try:
            fundamentals = load_fundamentals(tuple(sorted(usable)))
        except Exception as e:
            st.warning(f"Could not fetch valuation data: {e}")
            fundamentals = pd.DataFrame()

        if fundamentals is None or fundamentals.empty:
            st.info("No valuation data available for the selected symbols.")
        else:
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

    with rebalance_tab:
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

    with tearsheet_tab:
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
