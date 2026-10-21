"""The Import Portfolio page renders, and advertises the privacy default."""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

import pages.portfolio_import as portfolio_import
from utils import brokers

# AppTest resolves relative paths against the calling file, so pass an absolute
# path to the page.
ROOT = Path(__file__).resolve().parent.parent
IMPORT_PATH = ROOT / "pages" / "portfolio_import.py"
HARNESS = Path(__file__).resolve().parent / "_import_render_app.py"
LOCKED_CAS = Path(__file__).resolve().parent / "fixtures" / "holdings" / "cas-locked.pdf"


def _open_locked_statement():
    """Run the page with a password-protected CAS uploaded."""
    at = AppTest.from_file(str(HARNESS), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.file_uploader[0].upload(
        "cas-locked.pdf", LOCKED_CAS.read_bytes(), "application/pdf"
    )
    at.run()
    assert not at.exception, at.exception
    return at


def _button(at, label):
    return next(button for button in at.button if button.label == label)


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


def test_a_locked_statement_is_not_read_until_asked():
    """The password box reruns the page; it must not parse the PDF each time."""
    at = _open_locked_statement()

    assert not at.dataframe, "the statement was parsed before it was read"
    assert any("read the statement" in caption.value for caption in at.caption)


def test_a_wrong_password_leaves_the_read_button_in_place():
    at = _open_locked_statement()
    _button(at, "Read statement").click()
    at.run()

    assert not at.exception, at.exception
    assert not at.dataframe
    assert any(button.label == "Read statement" for button in at.button)


def test_reading_the_statement_keeps_the_preview_across_reruns():
    at = _open_locked_statement()
    at.text_input(key="import-cas-password").set_value("secret")
    at.run()
    _button(at, "Read statement").click()
    at.run()

    assert not at.exception, at.exception
    assert len(at.dataframe) == 1
    assert any(button.label == "Use this portfolio" for button in at.button)

    # A later rerun (another click, a changed name) reuses the session's result
    # instead of re-parsing the PDF.
    at.run()
    assert len(at.dataframe) == 1
