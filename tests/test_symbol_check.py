import unittest
import pandas as pd
import os
from unittest.mock import patch
from pathlib import Path
import sys

# Add project root to path to allow importing from utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Import the utility module
from utils import index_utils

# Define paths relative to this test file
TEST_DIR = os.path.dirname(__file__)
FIXTURES_DIR = os.path.join(TEST_DIR, 'fixtures')
DUMMY_INSTRUMENTS_PATH = os.path.join(FIXTURES_DIR, 'instruments.csv')

# Override the INDEX_PATH in the imported module to point to our test fixtures
index_utils.INDEX_PATH = Path(FIXTURES_DIR)

class TestSymbolCheck(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load dummy instruments data once for all tests."""
        try:
            cls.instruments_df = pd.read_csv(DUMMY_INSTRUMENTS_PATH)
        except FileNotFoundError:
            print(f"Error: Test instruments file not found at {DUMMY_INSTRUMENTS_PATH}")
            # Create a minimal DataFrame to allow tests to run without failing immediately
            cls.instruments_df = pd.DataFrame({'tradingsymbol': ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK']})

    # --- Tests for validate_symbols --- 
    def test_validate_symbols_all_valid(self):
        symbols = ['RELIANCE', 'TCS']
        expected = ['RELIANCE', 'TCS']
        actual = index_utils.validate_symbols(symbols, self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))

    def test_validate_symbols_mixed(self):
        symbols = ['RELIANCE', 'INVALID', 'INFY', 'NONEXISTENT']
        expected = ['RELIANCE', 'INFY']
        actual = index_utils.validate_symbols(symbols, self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))

    def test_validate_symbols_all_invalid(self):
        symbols = ['INVALID', 'NONEXISTENT']
        expected = []
        actual = index_utils.validate_symbols(symbols, self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))

    def test_validate_symbols_empty(self):
        symbols = []
        expected = []
        actual = index_utils.validate_symbols(symbols, self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))
        
    def test_validate_symbols_with_whitespace(self):
        symbols = [' RELIANCE ', 'TCS ', ' INFY'] # Symbols with extra spaces
        expected = [] # Expect empty as spaces make them invalid according to current validate_symbols
        actual_validate = index_utils.validate_symbols(symbols, self.instruments_df)
        self.assertListEqual(sorted(actual_validate), sorted(expected))

    # --- Tests for load_index_symbols --- 
    @patch('utils.index_utils.st') 
    def test_load_valid_index(self, mock_st):
        expected = ['RELIANCE', 'TCS']
        actual = index_utils.load_index_symbols("valid_index", self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))
        mock_st.warning.assert_not_called()
        mock_st.error.assert_not_called()

    @patch('utils.index_utils.st')
    def test_load_mixed_index(self, mock_st):
        expected = ['RELIANCE', 'INFY'] # Only valid symbols should be returned
        actual = index_utils.load_index_symbols("mixed_index", self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))
        mock_st.warning.assert_called_once()
        self.assertIn("Ignoring invalid/unknown symbols", mock_st.warning.call_args[0][0])
        self.assertIn("INVALID", mock_st.warning.call_args[0][0])
        self.assertIn("NONEXISTENT", mock_st.warning.call_args[0][0])
        mock_st.error.assert_not_called()

    @patch('utils.index_utils.st')
    def test_load_empty_index(self, mock_st):
        expected = []
        actual = index_utils.load_index_symbols("empty_index", self.instruments_df)
        self.assertListEqual(actual, expected)
        # Check that a warning was issued about the empty file
        mock_st.warning.assert_called_once_with("Index file is empty: empty_index.csv")
        mock_st.error.assert_not_called()

    @patch('utils.index_utils.st')
    def test_load_nonexistent_index(self, mock_st):
        expected = None
        actual = index_utils.load_index_symbols("nonexistent_index", self.instruments_df)
        self.assertIsNone(actual)
        mock_st.error.assert_called_once()
        self.assertIn("Index file not found", mock_st.error.call_args[0][0])
        self.assertIn("nonexistent_index.csv", mock_st.error.call_args[0][0])
        mock_st.warning.assert_not_called()
        
    @patch('utils.index_utils.st')
    def test_load_index_with_whitespace_symbols(self, mock_st):
        temp_file_path = index_utils.INDEX_PATH / "whitespace_index.csv"
        with open(temp_file_path, 'w') as f:
            f.write(" RELIANCE , TCS , , INFY ")
            
        expected = ['RELIANCE', 'TCS', 'INFY']
        actual = index_utils.load_index_symbols("whitespace_index", self.instruments_df)
        self.assertListEqual(sorted(actual), sorted(expected))
        mock_st.warning.assert_not_called()
        mock_st.error.assert_not_called()
        os.remove(temp_file_path)

if __name__ == '__main__':
    unittest.main(verbosity=2)
