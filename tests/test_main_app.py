"""Tests for the main Streamlit application."""

from streamlit.testing.v1 import AppTest

def test_smoke_main_app():
    """Basic smoke test to ensure the main app loads without exceptions."""
    at = AppTest.from_file("main.py", default_timeout=30) # Increased timeout for potentially slower CI environments
    at.run()
    assert not at.exception, f"App raised an exception during run: {at.exception}"

def test_main_app_elements():
    """Test for the presence of key elements on the main page."""
    at = AppTest.from_file("main.py", default_timeout=30)
    at.run()
    assert not at.exception, f"App raised an exception during run: {at.exception}"

    # Test for the title
    assert at.markdown[0].value == "# Welcome to The Trading Dashboard"

    # Page link assertions are removed due to AppTest limitations with st.page_link rendering as UnknownElement.
    # We can confirm the app runs and other elements are present.
    # Future: If AppTest enhances st.page_link support, these tests can be added.

    # Test for DATA.md content (check for a unique snippet)
    # DATA.md content is the last markdown element added by st.write(Path("DATA.md").read_text())
    # The title is markdown[0], separator is markdown[1]. So DATA.md should be markdown[2].
    # Using -1 is also robust if no other markdown is added later.
    assert "India Life Expectancy" in at.markdown[-1].value
    assert "[macrotrends.net](https://www.macrotrends.net/countries/IND/india/life-expectancy)" in at.markdown[-1].value
