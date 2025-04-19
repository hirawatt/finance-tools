import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from typing import Dict, Optional, Tuple
from plotly.graph_objs._figure import Figure

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
            if all(col in df.columns for col in REQUIRED_COLUMNS):
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
            use_container_width=True,
            hide_index=True
        )
    
    # Display Charts
    c1, c2 = st.columns(2)
    symbol_fig, sector_fig = create_charts(filtered_df, df_with_sectors)
    
    c1.subheader("Investment Distribution")
    c1.plotly_chart(symbol_fig, use_container_width=True)
    
    c2.subheader("Sector Distribution")
    c2.plotly_chart(sector_fig, use_container_width=True)

if __name__ == "__main__":
    main()