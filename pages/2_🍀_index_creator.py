import streamlit as st
import pandas as pd
import os, csv

index_path = os.getcwd() + "/indices/"

@st.cache
def load_data() -> pd.DataFrame:
    instruments = pd.read_csv("instruments")
    return instruments

def custom_indices() -> list:
    """Get List of Custom Indices from folder"""
    # Import Custom Indices
    indices_list = os.listdir(index_path)
    return indices_list

def index_symbols(instruments):
    """Generate Index Symbols from All Instruments"""
    st.write(instruments)
    # Select Instrument Exchange
    exchange = st.selectbox(
        "Select Instrument Exchange", instruments.exchange.unique().tolist(), index=3
    )  # index=3 'NSE' is default
    df = instruments[instruments["exchange"] == exchange]
    # Get all Stocks List
    stocks = df[
        (instruments["instrument_type"] == "EQ")
        & (instruments["lot_size"] == 1)
        & (instruments["tick_size"] == 0.05)
    ]
    st.write(stocks[["name", "tradingsymbol"]].dropna())

    st.subheader("TradingView Price Weighted Index")
    # TV Index from Custom Symbols
    # Select Symbols for Index
    with st.form("symbol_selection_form"):
        st.multiselect("Multiselect", stocks["name"])
        st.form_submit_button("Submit")

def custom_index_symbols() -> list:
    """Generate Index list from Custom Indices Folder"""
    indices_list = custom_indices()
    cIndex = st.sidebar.radio("Select Custom Index", indices_list)
    with open(index_path + cIndex) as f:
        reader = csv.reader(f)
        dfIndex = list(reader)
    symbols_list = dfIndex[0]
    return symbols_list

def tv_pw_index(symbols_list: list) -> str:
    """Display Trading View Price Weighted Index"""
    symbol = "NSE:" + "+NSE:".join(symbols_list)
    return symbol

# Watchlist Functions
@st.cache
def convert_df(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to CSV"""
    return df.to_csv().encode('utf-8')

def upload_download_file(watchlist):
    c1, c2 = st.columns(2)
    c1.file_uploader("Upload your watchlist file", type=['csv'], accept_multiple_files=False)
    c2.download_button(
        label="Download sample watchlist file",
        data=watchlist,
        file_name="./data/watchlist-sample.csv",
        mime='text/csv',
    )

def main():
    st.subheader("Watchlist")
    watchlist = pd.read_csv('./data/watchlist-sample.csv')
    custom = st.multiselect("Watchlist Stocks", watchlist.columns.to_list(), watchlist.columns.tolist())
    csv = convert_df(watchlist)
    upload_download_file(csv)

    st.markdown("---")
    st.subheader("Index Creator | Watchlist")
    instruments = load_data()
    # index_symbols(instruments)
    constituents = custom_index_symbols()
    st.multiselect("Stocks in Selected Index", constituents, constituents)
    # TV Index from Custom Index/Symbol
    st.info("Paste below symbol to TradingView")
    symbol = tv_pw_index(constituents)
    st.code(symbol, language="python")

    st.markdown("---")
    st.subheader("Sample Watchlists")
    cols = st.columns(4)
    for i, c in enumerate(cols):
        c.write("Watchlist 1")

if __name__ == "__main__":
    st.set_page_config(
        page_title="Index Creator | Watchlist",
        page_icon="🕴️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    main()
