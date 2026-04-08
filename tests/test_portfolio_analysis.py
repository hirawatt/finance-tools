import sys
from unittest.mock import MagicMock

# Create mock objects that behave like packages
class MockPackage(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__path__ = []

# Mock streamlit before importing portfolio_analysis
sys.modules["streamlit"] = MagicMock()

# Mock pandas
sys.modules["pandas"] = MagicMock()

# Mock plotly
sys.modules["plotly"] = MockPackage()
sys.modules["plotly.express"] = MagicMock()
sys.modules["plotly.graph_objs"] = MockPackage()
sys.modules["plotly.graph_objs._figure"] = MagicMock()

import unittest
from importlib.util import spec_from_file_location, module_from_spec

# Load the module
spec = spec_from_file_location("portfolio_analysis", "pages/3_💰_portfolio_analysis.py")
portfolio_analysis = module_from_spec(spec)
sys.modules["portfolio_analysis"] = portfolio_analysis
spec.loader.exec_module(portfolio_analysis)

class TestPortfolioAnalysis(unittest.TestCase):
    def test_process_portfolio_logic(self):
        """Verify the logic of process_portfolio by mocking pandas DataFrame interactions.
        This test ensures that the function correctly:
        1. Copies the input DataFrame.
        2. Sums the designated quantity columns.
        3. Calculates 'Invested Value' and 'Current Value' using the total quantity.
        4. Returns only the required columns.
        """
        import pandas as pd

        # 1. Create a mock DataFrame
        mock_df = MagicMock()
        mock_copy = MagicMock()
        mock_df.copy.return_value = mock_copy

        # 2. Mock behavior for quantity columns summation
        mock_loc = MagicMock()
        mock_copy.loc = mock_loc
        mock_quantity_cols_df = MagicMock()
        mock_loc.__getitem__.return_value = mock_quantity_cols_df

        mock_total_quantity = MagicMock()
        mock_quantity_cols_df.sum.return_value = mock_total_quantity

        # 3. Mock final selection
        mock_final_df = MagicMock()
        mock_copy.__getitem__.return_value = mock_final_df

        # 4. Define expected columns
        QUANTITY_COLUMNS = ['Quantity Available', 'Quantity Discrepant', 'Quantity Long Term',
                           'Quantity Pledged (Margin)', 'Quantity Pledged (Loan)']

        # EXECUTE
        result = portfolio_analysis.process_portfolio(mock_df)

        # VERIFY
        # Check copy was called to ensure no side effects on input
        mock_df.copy.assert_called_once()

        # Check Total Quantity calculation
        # Verify it uses the correct columns from QUANTITY_COLUMNS
        mock_loc.__getitem__.assert_called()
        args, _ = mock_loc.__getitem__.call_args
        self.assertEqual(args[0][1], QUANTITY_COLUMNS)
        mock_quantity_cols_df.sum.assert_called_with(axis='columns')

        # Check that 'Total Quantity' was assigned
        mock_copy.__setitem__.assert_any_call('Total Quantity', mock_total_quantity)

        # Check that 'Invested Value' and 'Current Value' were calculated and assigned
        # Since these involve multiplication with other columns, we check if __setitem__ was called
        # with these keys.
        mock_copy.__setitem__.assert_any_call('Invested Value', unittest.mock.ANY)
        mock_copy.__setitem__.assert_any_call('Current Value', unittest.mock.ANY)

        # Check final selection of columns
        mock_copy.__getitem__.assert_called()
        args, _ = mock_copy.__getitem__.call_args
        expected_selection = ['Symbol', 'Total Quantity', 'Invested Value', 'Current Value']
        self.assertEqual(args[0], expected_selection)

        self.assertEqual(result, mock_final_df)

    def test_module_constants(self):
        """Verify constants are correctly defined"""
        self.assertTrue(hasattr(portfolio_analysis, 'QUANTITY_COLUMNS'))
        self.assertTrue(hasattr(portfolio_analysis, 'REQUIRED_COLUMNS'))

if __name__ == '__main__':
    unittest.main()
