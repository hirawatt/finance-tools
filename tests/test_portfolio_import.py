"""The Import Portfolio page renders, and advertises the privacy default."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

# AppTest resolves relative paths against the calling file, so pass an absolute
# path to the page.
IMPORT_PATH = Path(__file__).resolve().parent.parent / "pages" / "portfolio_import.py"


def test_import_page_loads():
    at = AppTest.from_file(IMPORT_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"Page raised an exception: {at.exception}"


def test_import_page_offers_a_card_per_broker():
    at = AppTest.from_file(IMPORT_PATH, default_timeout=30)
    at.run()
    labels = {expander.label for expander in at.expander}
    assert {"Zerodha", "Groww", "Dhan", "Angel One"} <= labels


def test_import_page_states_the_privacy_default():
    at = AppTest.from_file(IMPORT_PATH, default_timeout=30)
    at.run()
    captions = " ".join(element.value for element in at.caption)
    assert "read in memory" in captions
    assert "nothing is written to disk" in captions
