"""Tests for the main Streamlit application."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

# Resolve the app entrypoint against the repo root. AppTest resolves relative
# paths against the file that calls it, so we pass an absolute path.
APP_PATH = Path(__file__).resolve().parent.parent / "main.py"

def test_smoke_main_app():
    """Basic smoke test to ensure the main app loads without exceptions."""
    at = AppTest.from_file(APP_PATH, default_timeout=30) # Increased timeout for potentially slower CI environments
    at.run()
    assert not at.exception, f"App raised an exception during run: {at.exception}"

def test_main_app_elements():
    """The home page renders its hero and the data guide."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"App raised an exception during run: {at.exception}"

    # The hero (and the shared stylesheet) are injected with st.html rather than
    # st.markdown, so the page's markdown elements stay reserved for real copy.
    html = " ".join(element.value for element in at.html)
    assert "The Trading Dashboard" in html

    # The data guide is written from DATA.md as markdown; check a unique snippet.
    # Joining every markdown element keeps this robust to the guide moving (it
    # lives in an expander) or to other copy being added around it.
    markdown = " ".join(element.value for element in at.markdown)
    assert "India Life Expectancy" in markdown
    assert "[macrotrends.net](https://www.macrotrends.net/countries/IND/india/life-expectancy)" in markdown
