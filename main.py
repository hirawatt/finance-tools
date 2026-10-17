"""The Trading Dashboard by Hirawat — Streamlit entrypoint.

The available pages are registered explicitly with :func:`st.navigation` and
:func:`st.Page` (rather than relying on the ``pages/`` directory's filename
convention), so each page's title, icon and order live in one place here. The
entrypoint is also the home page; page files under ``pages/`` must not call
``st.set_page_config`` (it may only run once per app).

Global presentation lives in :mod:`utils.theme`: the entrypoint injects the
stylesheet once, puts the brand in the sidebar and renders the shared footer.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from utils import theme

st.set_page_config(
    'The Trading Dashboard by Hirawat',
    # The committed SVG favicon, not an emoji, so the tab matches the brand.
    page_icon='assets/favicon.svg',
    layout='wide',
    initial_sidebar_state='expanded',
    menu_items={
        "Get Help": "https://github.com/hirawatt/finance-tools",
        "About": "Finance tools for Capital Markets",
        "Report a bug": "https://github.com/hirawatt/finance-tools/issues",
    },
)

# Colours, fonts and spacing come from .streamlit/config.toml; the stylesheet
# fills the gaps it cannot reach (hero, KPI/table/chart cards, footer).
theme.apply_theme()

# Brand lockup in the sidebar header, with the compact mark for the collapsed
# sidebar. Both are committed SVGs, so the container image needs no extra files.
st.logo("assets/logo.svg", size="large", icon_image="assets/logo-mark.svg")


@st.cache_data
def load_info() -> pd.DataFrame:
    """Load the dataset guide. Cached so the CSV is parsed once per process."""
    return pd.read_csv('./data/info.csv')


@st.cache_data
def dashboard_stats() -> dict[str, int]:
    """Headline counts for the home page, read from the committed data files."""
    sectors = pd.read_csv("./data/stock-sector.csv", usecols=["Sector"])["Sector"].nunique()
    with open("./data/all-companies-list.csv", encoding="utf-8") as handle:
        companies = max(sum(1 for _ in handle) - 1, 0)  # minus the header row
    return {
        "watchlists": len(list(Path("indices").glob("*.csv"))),
        "companies": companies,
        "sectors": int(sectors),
    }


def home() -> None:
    """Landing page: the hero, headline stats, the featured tools and the data guide."""
    theme.hero(
        eyebrow="Indian capital markets · NSE & BSE",
        title="The Trading Dashboard",
        subtitle=(
            "Capital-markets analysis for Indian portfolios, watchlists and trade "
            "ideas — the numbers that matter, without the noise."
        ),
        chips=(
            ("rocket_launch", "Co-Pilot portfolio analytics"),
            ("crisis_alert", "Red-flag & default-risk screening"),
            ("bedtime", "Nightly market-data snapshot"),
        ),
    )

    stats = dashboard_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Watchlists & portfolios", stats["watchlists"])
    c2.metric("Companies tracked", f"{stats['companies']:,}")
    c3.metric("Sectors covered", stats["sectors"])
    c4.metric("Tools & views", len(PAGES) - 2)  # every page but Home and About

    theme.section_header(
        "Featured tools",
        "Pick a desk — every view shares the same data guide at the bottom of this page.",
    )

    cards = (
        {
            "key": "td-card-copilot",
            "icon": "rocket_launch",
            "title": "Co-Pilot",
            "body": "Analyse, optimise and rebalance your portfolio.",
            "page": "pages/portfolio_analysis.py",
        },
        {
            "key": "td-card-ideas",
            "icon": "lightbulb",
            "title": "Idea Generation",
            "body": "Screen the market for trade candidates.",
            "page": "pages/stocks_to_trade.py",
        },
        {
            "key": "td-card-diligence",
            "icon": "troubleshoot",
            "title": "Due Diligence",
            "body": "Spot unusual activity before you commit.",
            "page": "pages/surprises.py",
        },
        {
            "key": "td-card-indices",
            "icon": "playlist_add_check",
            "title": "Index Creator",
            "body": "Build, edit and export watchlists, ready for TradingView.",
            "page": "pages/index_creator.py",
        },
        {
            "key": "td-card-search",
            "icon": "manage_search",
            "title": "Stock Search",
            "body": "Hunt small caps against a budget and an allocation cap.",
            "page": "pages/stock_search.py",
        },
        {
            "key": "td-card-tools",
            "icon": "calculate",
            "title": "Tools",
            "body": "Quick calculators for everyday trading maths.",
            "page": "pages/tools.py",
        },
    )

    for start in range(0, len(cards), 3):
        columns = st.columns(3)
        for column, card in zip(columns, cards[start : start + 3]):
            with column:
                theme.feature_card(**card)

    with st.expander("Data guide"):
        st.dataframe(load_info(), width="stretch", hide_index=True)
        st.write(Path("DATA.md").read_text())


# url_path is intentionally left unset on the file pages: Streamlit derives it
# from the filename, which keeps deep links stable across restarts.
PAGES = [
    st.Page(home, title="Home", icon=":material/space_dashboard:", default=True),
    st.Page("pages/portfolio_analysis.py", title="Co-Pilot", icon=":material/rocket_launch:"),
    st.Page("pages/stocks_to_trade.py", title="Idea Generation", icon=":material/lightbulb:"),
    st.Page("pages/surprises.py", title="Due Diligence", icon=":material/troubleshoot:"),
    st.Page("pages/index_creator.py", title="Index Creator", icon=":material/playlist_add_check:"),
    st.Page("pages/stock_search.py", title="Stock Search", icon=":material/manage_search:"),
    st.Page("pages/tools.py", title="Tools", icon=":material/calculate:"),
    st.Page("pages/about.py", title="About", icon=":material/info:"),
]


def main() -> None:
    st.navigation(PAGES).run()
    # Appended after the page body so every view ends with the same slim footer.
    theme.footer()


if __name__ == "__main__":
    main()
