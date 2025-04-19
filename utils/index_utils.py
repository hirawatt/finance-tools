import streamlit as st
import pandas as pd
import os
from pathlib import Path
from typing import List, Optional
import csv

# Path to the indices directory relative to the project root
# Assuming the script runs from the project root or utils/index_utils.py is imported correctly
try:
    # Try finding based on this file's location
    UTILS_DIR = Path(__file__).parent
    PROJECT_ROOT = UTILS_DIR.parent
except NameError:
    # Fallback if __file__ is not defined (e.g., interactive session)
    PROJECT_ROOT = Path(os.getcwd())

INDEX_PATH = PROJECT_ROOT / "indices"

def validate_symbols(symbols: List[str], instruments_df: pd.DataFrame) -> List[str]:
    """Validate symbols against the instruments dataframe's 'tradingsymbol' column."""
    if instruments_df is None or 'tradingsymbol' not in instruments_df.columns:
        # Handle cases where instruments_df is not loaded or malformed
        st.error("Instruments data is not available for validation.")
        return []
    valid_symbols_set = set(instruments_df['tradingsymbol'].tolist())
    # Assuming symbols in CSV and instruments are case-sensitive for now
    return [s for s in symbols if s in valid_symbols_set]

def load_index_symbols(index_file: str, instruments_df: pd.DataFrame) -> Optional[List[str]]:
    """Load symbols from index file, validate them, and handle errors."""
    file_path = INDEX_PATH / f"{index_file}.csv"
    try:
        with open(file_path) as f:
            reader = csv.reader(f)
            raw_symbols = next(reader)  # Get first row (assuming single row CSV)
            # Clean up symbols (remove potential whitespace)
            raw_symbols = [s.strip() for s in raw_symbols if s.strip()]
            if not raw_symbols:
                 st.warning(f"Index file appears empty or contains only whitespace: {index_file}.csv")
                 return []

            # Validate symbols
            valid_symbols = validate_symbols(raw_symbols, instruments_df)
            invalid_symbols = [s for s in raw_symbols if s not in valid_symbols]
            if invalid_symbols:
                st.warning(f"Ignoring invalid/unknown symbols found in {index_file}.csv: {', '.join(invalid_symbols)}")
            return valid_symbols
    except FileNotFoundError:
        st.error(f"Index file not found: {file_path}")
        return None
    except StopIteration:
        # This case might be covered by the cleanup check above, but keep for safety
        st.warning(f"Index file is empty: {index_file}.csv")
        return [] # Return empty list for empty file
    except Exception as e:
        st.error(f"Error loading index file {index_file}.csv: {e}")
        return None
