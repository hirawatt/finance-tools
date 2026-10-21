"""The Import Portfolio page renders, and advertises the privacy default."""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

import pages.portfolio_import as portfolio_import
from utils import brokers

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


def test_the_portfolio_name_is_applied_after_the_file_is_read():
    """The parse is cached without the name, so typing it does not re-read."""
    frame = pd.DataFrame({"Symbol": ["AAA"], "Total Quantity": [1]})
    parsed = brokers.BrokerImport(
        holdings=frame,
        resolved=frame,
        profile="Generic",
        source="holdings.csv",
        detected=False,
    )

    named = portfolio_import._with_client(parsed, "Dad's book")

    assert list(named.holdings["Client"]) == ["Dad's book"]
    # The cached result itself stays unnamed, so renaming never re-parses.
    assert "Client" not in parsed.holdings.columns
