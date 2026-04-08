import streamlit as st
import pandas as pd
import os
from pathlib import Path
from typing import List, Optional
import csv

from utils.custom_indices import INDEX_PATH, get_safe_path, custom_indices as get_indices

# Constants
DEFAULT_EXCHANGE = "NSE"

@st.cache_data
def get_custom_indices() -> List[str]:
    """Get list of custom indices"""
    return get_indices()

@st.cache_data
def load_instruments() -> pd.DataFrame:
    instruments = pd.read_csv("instruments")
    return instruments

@st.cache_data
def filter_tradable_stocks(instruments: pd.DataFrame, exchange: str) -> pd.DataFrame:
    """Filter tradable stocks based on criteria"""
    return instruments[
        (instruments["exchange"] == exchange) &
        (instruments["instrument_type"] == "EQ") &
        (instruments["lot_size"] == 1) &
        (instruments["tick_size"] == 0.05)
    ]

def load_index_symbols(index_file: str) -> Optional[List[str]]:
    """Load symbols from index file with error handling"""
    safe_path = get_safe_path(index_file)
    if not safe_path or not safe_path.exists():
        st.error(f"Error: Invalid index file or file not found.")
        return None

    try:
        with open(safe_path) as f:
            reader = csv.reader(f)
            return next(reader)  # Get first row
    except (FileNotFoundError, StopIteration) as e:
        st.error(f"Error loading index file: {e}")
        return None

def create_tv_index_string(symbols: List[str]) -> str:
    """Create TradingView index string"""
    return f"NSE:{'+NSE:'.join(symbols)}"

def handle_file_operations(watchlist: str):
    """Handle file upload and download operations"""
    col1, col2 = st.columns(2)
    
    # File Upload
    uploaded_file = col1.file_uploader(
        "Upload watchlist (CSV)",
        type=['csv'],
        help="Upload a CSV file with stock symbols"
    )
    
    if uploaded_file:
        try:
            # Process uploaded file
            df = pd.read_csv(uploaded_file)
            st.success("File uploaded successfully!")
            st.dataframe(df)
        except Exception as e:
            st.error(f"Error processing file: {e}")
    
    # File Download
    safe_path = get_safe_path(watchlist)
    if safe_path and safe_path.exists():
        try:
            with open(safe_path, "rb") as f:
                col2.download_button(
                    label="📥 Download current watchlist",
                    data=f,
                    file_name=f"{watchlist}.csv",
                    mime='text/csv',
                )
        except FileNotFoundError:
            col2.error("Watchlist file not found")
    else:
        col2.error("Watchlist file not found or invalid")

def main():
    st.title("🎯 Custom Index Creator & Watchlists")
    # Initialize session state
    if "instruments_df" not in st.session_state:
        st.session_state.instruments_df = load_instruments()
    
    # Use cached data
    instruments_df = st.session_state.instruments_df
    if instruments_df.empty:
        st.stop()
    
    # Index Selection
    indices_list = get_custom_indices()
    index_file = st.radio(
        "Select Index/Watchlist",
        indices_list,
        horizontal=True,
    )

    # Load and Display Index Constituents
    if constituents := load_index_symbols(index_file):
        selected_stocks = st.multiselect(
            "Manage Stocks in Selected Index/Watchlist",
            constituents,
            constituents,
            help="Select/deselect stocks to modify the index"
        )
        
        if selected_stocks != constituents:
            st.warning("You have modified the selection. Save changes?")
            if st.button("💾 Save Changes"):
                safe_path = get_safe_path(index_file)
                if safe_path:
                    try:
                        with open(safe_path, "w", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow(selected_stocks)
                        st.success("Changes saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error saving changes: {e}")
                else:
                    st.error("Invalid index file path.")
    
    # File Operations
    st.markdown("### 📁 File Operations")
    handle_file_operations(index_file)
    
    # TradingView Integration
    with st.sidebar:
        st.subheader("📊 TradingView Integration")
        if constituents:
            tv_symbol = create_tv_index_string(constituents)
            st.info("Copy this symbol to TradingView:")
            st.code(tv_symbol, language="text")

if __name__ == "__main__":
    st.set_page_config(
        page_title="Index Creator | Watchlist",
        page_icon="🕴️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    main()
