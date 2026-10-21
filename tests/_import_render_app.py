"""AppTest harness that runs the Import Portfolio page inside a navigation.

``pages/portfolio_import.py`` ends its preview with ``st.page_link`` to the
Co-Pilot, and Streamlit only resolves that when the target page is registered
with ``st.navigation`` — as ``main.py`` does. Rendering the page through this
harness lets a test drive the import flow the way a user does, instead of
failing on the link.

This is a script for ``AppTest.from_file``, not a test module (the leading
underscore keeps pytest from collecting it).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent

navigation = st.navigation(
    [
        st.Page(
            str(ROOT / "pages" / "portfolio_import.py"),
            title="Import Portfolio",
            default=True,
        ),
        st.Page(str(ROOT / "pages" / "portfolio_analysis.py"), title="Co-Pilot"),
    ]
)
navigation.run()
