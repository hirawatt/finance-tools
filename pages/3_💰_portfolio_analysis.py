import streamlit as st
from streamlit import caching

import pandas as pd
from pathlib import Path

import seaborn as sns

@st.experimental_memo
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Drop Unrequired Rows and Columns"""

    df1 = df.drop(columns=['ISIN', 'Quantity Available', 'Sector', 'Quantity Discrepant', 'Quantity Long Term', 'Quantity Pledged (Margin)', 'Quantity Pledged (Loan)'])
    df1 = df1.drop([0])

    df1['Total Quantity'] = df['Quantity Available'] + df['Quantity Discrepant'] + df['Quantity Long Term'] + df['Quantity Pledged (Margin)'] + df['Quantity Pledged (Loan)']
    df1['Invested Value'] = df1['Total Quantity'] * df1['Average Price']
    df1['Current Value']  = df1['Total Quantity'] * df1['Previous Closing Price']
    
    #st.dataframe(df1)
    return df1

# TD: Add Logic to this Function
def live_prices(symbol_selections: list) -> None:
    """Display Live Prices"""

    st.subheader("Live Prices Updated")

    st.write(symbol_selections)

def investment_display_info(df: pd.DataFrame) -> None:
    """Display Investment Info"""

    pnl = round(df['Current Value'].sum() - df['Invested Value'].sum())
    pct_change = round((pnl / df['Invested Value'].sum()) * 100, 2)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Total Investment', value=round(df['Invested Value'].sum()))
    c2.metric('Current Value', value=round(df['Current Value'].sum()))
    c3.metric('Total P&L', value=pnl, delta='{}%'.format(pct_change))

    
def main() -> None:
    st.header('🚀 Co-Pilot')
    with st.expander("How to Use This"):
        st.write(Path("HOW_TO_USE.md").read_text())
    
    st.subheader("Upload Holdings from Zerodha [Family](https://console.zerodha.com/portfolio/holdings/family)/[Personal](https://console.zerodha.com/portfolio/holdings/)")
    uploaded_file = st.file_uploader("Drag and Drop or Click to Upload", type=['xlsx'], accept_multiple_files=False)

    if uploaded_file is None:
        st.info("Using example data. Upload a file above to use your own data!")
        portfolio = pd.read_excel('./data/holdings-sample.xlsx', header=22, usecols="B:L")
    else:
        st.success("Uploaded your file!")
        file_details = {"FileName":uploaded_file.name,"FileType":uploaded_file.type,"FileSize":uploaded_file.size}
        st.write(file_details)
        portfolio = pd.read_excel(uploaded_file.name, header=22, usecols="B:L")
    
    with st.expander("Raw Dataframe"):
        st.write(portfolio)

    df = clean_data(portfolio)
    with st.expander("Cleaned Data"):
        st.write(df)
    
    # Implement when download for family holdings is available
    #st.sidebar.subheader("Filter Displayed Accounts")

    # Select Tickers to Display
    st.sidebar.subheader("Filter Displayed Tickers")
    symbol_selections = st.sidebar.multiselect("Select Ticker Symbols to View", options=df["Symbol"], default=df["Symbol"])

    investment_display_info(df)

if __name__ == "__main__":
    st.set_page_config(
        "Zerodha Portfolio Analysis",
        ":moneybag:",
        initial_sidebar_state="expanded",
        layout="wide",
    )
    main()