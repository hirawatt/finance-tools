import streamlit as st
import pandas as pd
import os, csv

import src.custom_indices as custom_indices

index_path = os.getcwd() + "/indices/"

@st.cache
def load_data() -> pd.DataFrame:
    instruments = pd.read_csv("instruments")
    return instruments

@st.cache
def ci() -> list:
    return custom_indices.custom_indices()

def index_symbols(instruments: pd.DataFrame) -> list:
    """Generate Index Symbols from All Instruments"""
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

    with st.expander("Data Preview"):
        st.write(instruments)
        st.write(stocks[["name", "tradingsymbol"]].dropna())

    st.subheader("TradingView Price Weighted Index")
    # TV Index from Custom Symbols
    # Select Symbols for Index
    with st.form("symbol_selection_form"):
        st.multiselect("Multiselect", stocks["name"])
        st.form_submit_button("Submit")
    
    return stocks["tradingsymbol"].tolist()

def custom_index_symbols(cIndex: str) -> list:
    """Return contents of Custom Index sent as Argument"""
    with open(index_path + cIndex) as f:
        reader = csv.reader(f)
        dfIndex = list(reader)
    symbols_list = dfIndex[0]
    return symbols_list

def tv_pw_index(symbols_list: list) -> str:
    """Display Trading View Price Weighted Index"""
    symbol = "NSE:" + "+NSE:".join(symbols_list)
    return symbol

def upload_download_file(watchlist):
    """Streamlit Upload/Download File

    Args:
        watchlist (str): custom index/watchlist filename
    """
    c1, c2 = st.columns(2)
    c1.file_uploader("Upload your watchlist file", type=['csv'], accept_multiple_files=False)
    with open("./indices/{}.csv".format(watchlist), "rb") as f:
        c2.download_button(
            label="Download sample watchlist file",
            data=f,
            file_name="{}.csv".format(watchlist),
            mime='text/csv',
        )

def main():
    st.subheader(":first_place_medal: Custom Index Creator | Watchlists")
    indices_list = ci()
    index_file = st.radio("Select Index | Watchlist", indices_list, horizontal=True)

    instruments = load_data()
    #index_symbols(instruments)
    constituents = custom_index_symbols(index_file + '.csv')
    st.multiselect("Stocks in Selected Index | Watchlist", constituents, constituents)
    upload_download_file(index_file)

    st.markdown("---")
    # Basket to buy NIFTY 50 as an ETF
    


    # TV Index from Custom Index/Symbol
    st.sidebar.subheader(":second_place_medal: TradingView Price Weighted Index")
    st.sidebar.info("Paste below symbol to TradingView")
    symbol = tv_pw_index(constituents)
    st.sidebar.code(symbol, language="python")
    st.sidebar.markdown("---")

if __name__ == "__main__":
    st.set_page_config(
        page_title="Index Creator | Watchlist",
        page_icon="🕴️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    main()
