"""Custom index creator and watchlists.

A watchlist is a one-line CSV of NSE symbols under ``indices/``; this page edits
one, moves watchlists in and out as CSVs, and turns the current list into a
TradingView symbol string.
"""

import csv
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

from utils import theme
from utils.custom_indices import get_safe_path, custom_indices as get_indices


@st.cache_data
def get_custom_indices() -> List[str]:
    """Get list of custom indices"""
    return get_indices()


@st.cache_data
def load_instruments() -> pd.DataFrame:
    """The Kite instruments dump, loaded once per process."""
    return pd.read_csv("instruments")


def resolve_watchlist(index_file: str) -> Optional[Path]:
    """The existing file for ``index_file``, or ``None`` when it is unusable."""
    path = get_safe_path(index_file)
    return path if path and path.exists() else None


def load_index_symbols(index_file: str) -> Optional[List[str]]:
    """Load symbols from index file with error handling"""
    path = resolve_watchlist(index_file)
    if path is None:
        st.error("Error: Invalid index file or file not found.")
        return None

    try:
        with open(path) as f:
            reader = csv.reader(f)
            return next(reader)  # Get first row
    except (FileNotFoundError, StopIteration) as e:
        st.error(f"Error loading index file: {e}")
        return None


def save_index_symbols(index_file: str, symbols: List[str]) -> None:
    """Write ``symbols`` back to the watchlist, reporting why if it fails.

    Saving intentionally does not require the file to exist: the path is what
    matters, and ``open(..., "w")`` recreates a watchlist that was removed.
    """
    path = get_safe_path(index_file)
    if not path:
        st.error("Invalid index file path.")
        return

    try:
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(symbols)
        st.success("Changes saved successfully!")
        st.rerun()
    except Exception as e:
        st.error(f"Error saving changes: {e}")


def create_tv_index_string(symbols: List[str]) -> str:
    """Create TradingView index string"""
    return f"NSE:{'+NSE:'.join(symbols)}"


def upload_watchlist() -> None:
    """Read an uploaded watchlist CSV and show what it contains."""
    uploaded_file = st.file_uploader(
        "Upload watchlist (CSV)",
        type=['csv'],
        help="Upload a CSV file with stock symbols"
    )
    if not uploaded_file:
        return

    try:
        df = pd.read_csv(uploaded_file)
        st.success("File uploaded successfully!")
        st.dataframe(df, alt="Uploaded watchlist preview")
    except Exception as e:
        st.error(f"Error processing file: {e}")


def download_watchlist(index_file: str) -> None:
    """Offer the current watchlist as a CSV download."""
    path = resolve_watchlist(index_file)
    if path is None:
        st.error("Watchlist file not found or invalid")
        return

    try:
        with open(path, "rb") as f:
            st.download_button(
                label="Download current watchlist",
                data=f,
                file_name=f"{index_file}.csv",
                mime='text/csv',
                icon=":material/download:",
            )
    except FileNotFoundError:
        st.error("Watchlist file not found")


def instruments() -> pd.DataFrame:
    """The instruments dump, cached in session state as a readiness check."""
    if "instruments_df" not in st.session_state:
        st.session_state.instruments_df = load_instruments()
    return st.session_state.instruments_df


def edit_watchlist(index_file: str) -> Optional[List[str]]:
    """Show the constituents and save them when the selection changed."""
    constituents = load_index_symbols(index_file)
    if not constituents:
        return None

    selected_stocks = st.multiselect(
        "Manage stocks in the selected index/watchlist",
        constituents,
        constituents,
        help="Select/deselect stocks to modify the index"
    )

    if selected_stocks != constituents:
        st.warning("You have modified the selection. Save changes?")
        if st.button("Save changes", type="primary", icon=":material/save:"):
            save_index_symbols(index_file, selected_stocks)

    return constituents


def tradingview_panel(constituents: Optional[List[str]]) -> None:
    """Where to paste the watchlist in TradingView, for the sidebar."""
    with st.sidebar:
        theme.section_header("TradingView integration")
        if constituents:
            st.info("Copy this symbol to TradingView:")
            st.code(create_tv_index_string(constituents), language="text")


def main():
    theme.page_header(
        "Custom Index Creator & Watchlists",
        "Build, edit and export the watchlists the other desks read.",
    )

    instruments_df = instruments()
    if instruments_df.empty:
        st.stop()

    # Thirty-odd watchlists is far past what a radio group can show at once, so
    # the choice lives in a dropdown.
    index_file = st.selectbox(
        "Select index/watchlist",
        get_custom_indices(),
    )

    constituents = edit_watchlist(index_file)

    theme.section_header("File operations")
    upload_column, download_column = st.columns(2)
    with upload_column:
        upload_watchlist()
    with download_column:
        download_watchlist(index_file)

    tradingview_panel(constituents)


if __name__ == "__main__":
    main()
