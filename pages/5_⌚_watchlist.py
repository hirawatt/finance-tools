import streamlit as st
import pandas as pd

@st.cache
def convert_df(df):
    # IMPORTANT: Cache the conversion to prevent computation on every rerun
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
    watchlist = pd.read_csv('./data/watchlist-sample.csv')
    custom = st.multiselect("Watchlist Stocks", watchlist.columns.to_list(), watchlist.columns.tolist())
    csv = convert_df(watchlist)
    upload_download_file(csv)

    st.subheader("Sample Watchlists")
    cols = st.columns(4)
    for i, c in enumerate(cols):
        c.write("Watchlist 1")

if __name__ == "__main__":
    st.set_page_config(
        "Watchlist",
        "🕴️",
        initial_sidebar_state="expanded",
        layout="wide",
    )
    main()