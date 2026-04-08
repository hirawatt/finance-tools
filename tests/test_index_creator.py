import pytest
from unittest.mock import patch, MagicMock, mock_open, call
import sys

# Mock pandas, streamlit, and other dependencies to avoid ModuleNotFoundError
mock_pd = MagicMock()
sys.modules['pandas'] = mock_pd
mock_st = MagicMock()
sys.modules['streamlit'] = mock_st

import importlib.util
spec = importlib.util.spec_from_file_location("index_creator", "pages/2_🍀_index_creator.py")
index_creator = importlib.util.module_from_spec(spec)
sys.modules["index_creator"] = index_creator
spec.loader.exec_module(index_creator)

def test_load_index_symbols_valid():
    with patch('index_creator.get_safe_path') as mock_get_safe_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_safe_path.return_value = mock_path

        m_open = mock_open(read_data="AAPL,MSFT,GOOGL\n")
        with patch('builtins.open', m_open):
            result = index_creator.load_index_symbols("test_index")
            assert result == ["AAPL", "MSFT", "GOOGL"]

def test_save_functionality_in_main():
    # Reset mock_st methods
    mock_st.reset_mock()

    # Setup st session state properly as an object with dict-like and attribute-like access
    class SessionState(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                raise AttributeError(key)
        def __setattr__(self, key, value):
            self[key] = value

    mock_st.session_state = SessionState()
    mock_df = MagicMock()
    mock_df.empty = False
    mock_st.session_state.instruments_df = mock_df
    mock_st.radio.return_value = "test_index"

    # Mock st.columns to return exactly 2 items
    col1 = MagicMock()
    col2 = MagicMock()
    mock_st.columns.return_value = (col1, col2)
    col1.file_uploader.return_value = None # Don't trigger the file upload success logic

    with patch('index_creator.get_custom_indices', return_value=["test_index"]), \
         patch('index_creator.load_index_symbols', return_value=["AAPL", "MSFT"]), \
         patch('index_creator.get_safe_path') as mock_get_safe_path:

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_safe_path.return_value = mock_path

        # Mock UI interactions
        mock_st.multiselect.return_value = ["AAPL", "MSFT", "GOOGL"] # User added GOOGL
        mock_st.button.return_value = True # User clicked save

        m_open = mock_open()
        with patch('builtins.open', m_open):
            # Run the main function
            index_creator.main()

            # Verify file was written
            m_open.assert_any_call(mock_path, "w", newline="")

            # Verify success message and rerun were called
            mock_st.success.assert_any_call("Changes saved successfully!")
            mock_st.rerun.assert_called_once()
