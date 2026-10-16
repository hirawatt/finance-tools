import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from unittest.mock import MagicMock


class MockPackage(MagicMock):
    """A MagicMock that also behaves like a package (has ``__path__``)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__path__ = []


_MISSING = object()
_pre_existing_modules = set(sys.modules)


def _forget_parent_attribute(name: str, module) -> None:
    """Drop a submodule's attribute from its parent package.

    Removing an entry from ``sys.modules`` is not enough: importing a submodule
    also binds it as an attribute of its parent, and ``from utils import x``
    resolves that attribute before it consults ``sys.modules``. Without this the
    next test module would receive the stale, mock-backed module.
    """
    parent_name, _, child = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None and getattr(parent, child, None) is module:
        delattr(parent, child)

# The page imports pandas/streamlit/plotly at import time. Stub them only while
# the module is being loaded, then restore whatever was there before so the real
# packages stay untouched for other tests in the same process.
_OVERRIDES = {
    "streamlit": MagicMock(),
    "pandas": MagicMock(),
    "plotly": MockPackage(),
    "plotly.express": MagicMock(),
    "plotly.graph_objs": MockPackage(),
    "plotly.graph_objs._figure": MagicMock(),
}
_saved_modules = {name: sys.modules.get(name, _MISSING) for name in _OVERRIDES}

sys.modules.update(_OVERRIDES)
try:
    spec = spec_from_file_location("portfolio_analysis", "pages/portfolio_analysis.py")
    portfolio_analysis = module_from_spec(spec)
    sys.modules["portfolio_analysis"] = portfolio_analysis
    spec.loader.exec_module(portfolio_analysis)
finally:
    # Drop any module imported while pandas was stubbed (e.g. utils.snapshot),
    # so nothing caches a mock reference for later test modules. Both the
    # sys.modules entry and the parent-package attribute have to go.
    for name in set(sys.modules) - _pre_existing_modules:
        _forget_parent_attribute(name, sys.modules.pop(name, None))
    for name, original in _saved_modules.items():
        if original is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


class TestPortfolioAnalysis(unittest.TestCase):
    def test_process_portfolio_logic(self):
        """Verify the logic of process_portfolio by mocking pandas DataFrame interactions.
        This test ensures that the function correctly:
        1. Copies the input DataFrame.
        2. Sums the designated quantity columns.
        3. Calculates 'Invested Value' and 'Current Value' using the total quantity.
        4. Returns only the required columns.
        """
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
