"""The About page must render with no secrets configured.

The published container image ships without a `.streamlit/secrets.toml`, so the
credits have to come from a fallback instead of a required `[credits]` table.
"""

from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

import pages.about as about

# AppTest resolves relative paths against the file that calls it, so we pass an
# absolute path (see AGENTS.md).
ABOUT_PATH = Path(__file__).resolve().parent.parent / "pages" / "about.py"


def test_about_page_renders_without_secrets():
    at = AppTest.from_file(ABOUT_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"App raised an exception during run: {at.exception}"
    # The credits line is injected with st.html, so the page's markdown elements
    # stay reserved for copy.
    html = " ".join(element.value for element in at.html)
    assert "Made with" in html


def test_credits_merge_over_fallbacks(monkeypatch):
    monkeypatch.setattr(st, "secrets", {"credits": {"name": "Someone"}}, raising=False)

    merged = about.credits()

    assert merged["name"] == "Someone"
    assert merged["website"] == about.FALLBACK_CREDITS["website"]


def test_credits_fall_back_when_table_is_missing(monkeypatch):
    monkeypatch.setattr(st, "secrets", {}, raising=False)

    assert about.credits() == about.FALLBACK_CREDITS
