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

#: Registered pages that frame the app rather than being a tool of their own.
FRAME_PAGES = 2  # Home and About

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
st.logo("assets/logo.svg", size="large", icon_image="assets/favicon.svg")


@st.cache_data
def load_info() -> pd.DataFrame:
    """Load the dataset guide. Cached so the CSV is parsed once per process."""
    return pd.read_csv('./data/info.csv')


@st.cache_data
def company_count() -> int:
    """Rows in the committed company master (the header line excluded)."""
    with open("./data/all-companies-list.csv", encoding="utf-8") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


@st.cache_data
def sector_count() -> int:
    """Distinct sectors in the committed sector map."""
    sectors = pd.read_csv("./data/stock-sector.csv", usecols=["Sector"])["Sector"]
    return int(sectors.nunique())


def dashboard_stats() -> dict[str, int]:
    """Headline counts for the home page.

    Only the committed data files are cached: the watchlist count is a live
    directory listing, so a list added or removed under ``indices/`` shows up
    without a restart.
    """
    return {
        "watchlists": len(list(Path("indices").glob("*.csv"))),
        "companies": company_count(),
        "sectors": sector_count(),
    }


def home() -> None:
    """Landing page: the hero, headline stats, the workflow, the tools and the data guide."""
    theme.hero(
        eyebrow="Indian equities · NSE & BSE",
        title="One desk for Indian market analytics",
        subtitle=(
            "Portfolio analysis, red-flag screening and trade ideas for NSE and "
            "BSE — the numbers that matter, without the noise."
        ),
        chips=(
            ("rocket_launch", "Portfolio Co-Pilot"),
            ("crisis_alert", "Red-flag screening"),
            ("bedtime", "Nightly data snapshot"),
        ),
        mark="assets/app-icon.svg",
        name="The Trading Dashboard",
        byline="By Hirawat",
        graphic="assets/hero-graphic.svg",
    )

    stats = dashboard_stats()
    theme.metric_row(
        (
            ("Watchlists & portfolios", stats["watchlists"]),
            ("Companies tracked", f"{stats['companies']:,}"),
            ("Sectors covered", stats["sectors"]),
            ("Tools & views", len(PAGES) - FRAME_PAGES),
        )
    )

    theme.section_header(
        "What you can do here",
        "One desk for the whole workflow — from your holdings to a shortlist.",
    )
    theme.steps(
        (
            (
                "upload_file",
                "Bring your portfolio",
                "Upload holdings or open a watchlist; the Co-Pilot reads positions, weights and costs.",
            ),
            (
                "insights",
                "Analyse & optimise",
                "Sector and stock weights, beta, correlation and PE — then rebalancing ideas.",
            ),
            (
                "travel_explore",
                "Screen & decide",
                "Hunt trade candidates and unusual activity across the market.",
            ),
            (
                "cloud_sync",
                "Stay current",
                "A nightly snapshot of the universe keeps every view fast and fresh.",
            ),
        )
    )

    theme.section_header(
        "Featured tools",
        "Pick a desk — every view shares the same data guide at the bottom of this page.",
    )

    cards = (
        {
            "key": "td-card-import",
            "icon": "upload_file",
            "title": "Import Portfolio",
            "body": "Bring holdings from Zerodha, Groww, Dhan or Angel One.",
            "page": "pages/portfolio_import.py",
        },
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
        {
            "key": "td-card-directory",
            "icon": "apps",
            "title": "Tool Directory",
            "body": "Every platform we use, in one linked grid.",
            "page": "pages/tool_directory.py",
        },
    )

    for start in range(0, len(cards), 3):
        columns = st.columns(3)
        for column, card in zip(columns, cards[start : start + 3]):
            with column:
                theme.feature_card(**card)

    with st.expander("Data guide"):
        st.dataframe(load_info(), hide_index=True, alt="Data source guide")
        st.markdown(Path("DATA.md").read_text())


# url_path is intentionally left unset on the file pages: Streamlit derives it
# from the filename, which keeps deep links stable across restarts.
PAGES = [
    st.Page(home, title="Home", icon=":material/space_dashboard:", default=True),
    st.Page("pages/portfolio_import.py", title="Import Portfolio", icon=":material/upload_file:"),
    st.Page("pages/portfolio_analysis.py", title="Co-Pilot", icon=":material/rocket_launch:"),
    st.Page("pages/stocks_to_trade.py", title="Idea Generation", icon=":material/lightbulb:"),
    st.Page("pages/surprises.py", title="Due Diligence", icon=":material/troubleshoot:"),
    st.Page("pages/index_creator.py", title="Index Creator", icon=":material/playlist_add_check:"),
    st.Page("pages/stock_search.py", title="Stock Search", icon=":material/manage_search:"),
    st.Page("pages/tools.py", title="Tools", icon=":material/calculate:"),
    st.Page("pages/tool_directory.py", title="Tool Directory", icon=":material/apps:"),
    st.Page("pages/about.py", title="About", icon=":material/info:"),
]


def main() -> None:
    st.navigation(PAGES).run()
    # Appended after the page body so every view ends with the same slim footer.
    theme.footer()


if __name__ == "__main__":
    main()
