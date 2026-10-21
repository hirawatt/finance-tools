"""Idea Generation — screen the market for trade candidates."""

import streamlit as st

from utils import theme


def main() -> None:
    theme.page_header(
        "Idea Generation",
        "Shortlist trade candidates by the conditions that matter to you.",
    )

    # The screen is not built yet. An inert set of filters looked like a working
    # control and changed nothing, so the page says so instead and points at the
    # views that already answer the question.
    st.info(
        "This desk is not wired up yet — no filter here affects the market data. "
        "Until it is, Due Diligence covers unusual activity and Stock Search "
        "screens small-caps against a budget.",
        title="Coming soon",
    )

    with st.container(horizontal=True):
        st.page_link(
            "pages/surprises.py",
            label="Due Diligence",
            icon=":material/troubleshoot:",
        )
        st.page_link(
            "pages/stock_search.py",
            label="Stock Search",
            icon=":material/manage_search:",
        )


if __name__ == "__main__":
    main()
