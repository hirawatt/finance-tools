import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock

from _stubs import stubbed


class MockPackage(MagicMock):
    """A MagicMock that also behaves like a package (has ``__path__``)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__path__ = []


# The page imports pandas/streamlit/the chart builders at import time, and the
# builders import plotly.graph_objects. Stub them only while the module is being
# loaded, so the real packages stay untouched for other tests in the same process.
_OVERRIDES = {
    "streamlit": MagicMock(),
    "pandas": MagicMock(),
    "plotly": MockPackage(),
    "plotly.express": MagicMock(),
    "plotly.graph_objects": MockPackage(),
    "plotly.graph_objs": MockPackage(),
    "plotly.graph_objs._figure": MagicMock(),
}

with stubbed("portfolio_analysis", **_OVERRIDES):
    spec = spec_from_file_location("portfolio_analysis", "pages/portfolio_analysis.py")
    portfolio_analysis = module_from_spec(spec)
    sys.modules["portfolio_analysis"] = portfolio_analysis
    spec.loader.exec_module(portfolio_analysis)


class TestPortfolioAnalysis(unittest.TestCase):
    def test_printf_format_translates_python_specs(self):
        """Format specs become printf strings for st.column_config.NumberColumn."""
        translate = portfolio_analysis.printf_format
        self.assertEqual(translate("₹{:,.0f}"), "₹%,.0f")
        self.assertEqual(translate("₹{:,.2f}"), "₹%,.2f")
        self.assertEqual(translate("{:.1f}%"), "%.1f%%")
        self.assertEqual(translate("{:+,.0f}"), "%+,.0f")
        self.assertEqual(translate("{:.2f}"), "%.2f")

    def test_analytics_sections_cover_the_expected_views(self):
        """Every analytics view stays registered, in a stable order."""
        self.assertEqual(
            portfolio_analysis.ANALYTICS_SECTIONS,
            (
                "Correlation",
                "Beta & Risk",
                "Valuation",
                "Risk Flags",
                "Rebalance",
                "Outlook",
                "Tearsheet",
            ),
        )

    def test_the_page_reuses_the_shared_import_reader(self):
        """The page reads holdings through the broker importer, not a hard-coded header."""
        source = Path("pages/portfolio_analysis.py").read_text()
        self.assertIn("brokers.import_holdings", source)
        self.assertNotIn("header=22", source)


if __name__ == '__main__':
    unittest.main()
