"""The Trading Dashboard by Hirawat — Streamlit entrypoint.

The available pages are registered explicitly with :func:`st.navigation` and
:func:`st.Page` (rather than relying on the ``pages/`` directory's filename
convention), so each page's title, icon and order live in one place here. The
entrypoint is also the home page; page files under ``pages/`` must not call
``st.set_page_config`` (it may only run once per app).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    'The Trading Dashboard by Hirawat',
    '🕴️',
    layout='wide',
    initial_sidebar_state='expanded',
    menu_items={
        "Get Help": "https://github.com/hirawatt/finance-tools",
        "About": "Finance tools for Capital Markets",
        "Report a bug": "https://github.com/hirawatt/finance-tools/issues",
    },
)


@st.cache_data
def load_info() -> pd.DataFrame:
    """Load the dataset guide. Cached so the CSV is parsed once per process."""
    return pd.read_csv('./data/info.csv')


def home() -> None:
    """Landing page: the featured tools and the dataset guide."""
    st.write("# Welcome to The Trading Dashboard")
    st.caption(
        "Capital-markets analysis for Indian portfolios, watchlists and trade ideas."
    )

    st.subheader("Featured tools")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.page_link("pages/portfolio_analysis.py", label="🚀 Co-Pilot", width="stretch")
        st.caption("Analyse, optimise and rebalance your portfolio.")
    with c2:
        st.page_link("pages/stocks_to_trade.py", label="💡 Idea Generation", width="stretch")
        st.caption("Screen the market for trade candidates.")
    with c3:
        st.page_link("pages/surprises.py", label="🚦 Due Diligence", width="stretch")
        st.caption("Spot unusual activity before you commit.")

    with st.expander("🗂️ Data guide"):
        st.dataframe(load_info(), width="stretch", hide_index=True)
        st.write(Path("DATA.md").read_text())


# url_path is intentionally left unset on the file pages: Streamlit derives it
# from the filename, which keeps deep links stable across restarts.
PAGES = [
    st.Page(home, title="Home", icon="🕴️", default=True),
    st.Page("pages/portfolio_analysis.py", title="Co-Pilot", icon="🚀"),
    st.Page("pages/stocks_to_trade.py", title="Idea Generation", icon="💡"),
    st.Page("pages/surprises.py", title="Due Diligence", icon="🚦"),
    st.Page("pages/index_creator.py", title="Index Creator", icon="🍀"),
    st.Page("pages/stock_search.py", title="Stock Search", icon="❄️"),
    st.Page("pages/tools.py", title="Tools", icon="💸"),
    st.Page("pages/about.py", title="About", icon="🕴️"),
]


def main() -> None:
    st.navigation(PAGES).run()


if __name__ == "__main__":
    main()
