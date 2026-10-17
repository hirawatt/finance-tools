"""Tool Directory — a logo wall of external platforms for Indian markets.

A curated grid of the sites we reach for around this dashboard: screeners,
research, journals, macro data and automation. Each card is an outbound link to
the vendor's own site; nothing here fetches or embeds their content.

The entries are plain data — :data:`TOOLS` — rendered by :func:`theme.tool_grid`.
Logos are committed under ``assets/logos/`` (see that folder's README) and
inlined as data URIs by the renderer; an entry with no usable logo falls back to
an initials tile, so a missing file never leaves a broken image.
"""

import streamlit as st

from utils import theme

#: The directory, in the order it should read. Each entry maps ``name``,
#: ``url``, ``description`` and ``tag``, with an optional ``logo`` (a path
#: relative to the repository root) and an ``initials`` fallback.
TOOLS = (
    {
        "name": "Trading Economics",
        "url": "https://tradingeconomics.com/",
        "tag": "Macro data",
        "logo": "assets/logos/tradingeconomics.svg",
        "description": "Economic indicators, forecasts and charts for 200+ economies, India included.",
    },
    {
        "name": "Toggle",
        "url": "https://toggle.ai/",
        "tag": "AI research",
        "logo": "assets/logos/toggle.png",
        "description": "AI analyst that answers market questions in plain language.",
    },
    {
        "name": "Intraday Screener",
        "url": "https://intradayscreener.com/app/login",
        "tag": "Screener",
        "logo": "assets/logos/intradayscreener.svg",
        "description": "Real-time intraday scanners for Indian equities and futures.",
    },
    {
        "name": "Harmoney",
        "url": "https://www.harmoney.in/",
        "tag": "Fixed income",
        "logo": "assets/logos/harmoney.png",
        "description": "Bond and fixed-income workflows for Indian markets; now rebranding to InferEdge.",
    },
    {
        "name": "Spider Software",
        "url": "https://www.spidersoftwareindia.com/",
        "tag": "Trading software",
        "logo": "assets/logos/spidersoftware.png",
        "description": "Charting, backtesting and algo terminals for Indian brokers.",
    },
    {
        "name": "AnaStrat",
        "url": "https://www.anastrat.com/",
        "tag": "Analytics",
        "initials": "AS",
        "description": "AI post-trade analytics and a trading journal that score your behaviour.",
    },
    {
        "name": "3Commas",
        "url": "https://3commas.io/",
        "tag": "Automation",
        "logo": "assets/logos/3commas.png",
        "description": "Crypto trading bots, smart trades and portfolio automation.",
    },
    {
        "name": "MarketBeat",
        "url": "https://www.marketbeat.com/",
        "tag": "Research",
        "logo": "assets/logos/marketbeat.png",
        "description": "Analyst ratings, earnings coverage and screeners, weighted to US markets.",
    },
    {
        "name": "StocksEmoji",
        "url": "https://stocksemoji.com/",
        "tag": "Research",
        "logo": "assets/logos/stocksemoji.png",
        "description": "Fundamental research, a screener and a portfolio optimiser with a score for every stock.",
    },
    {
        "name": "Swift Journal",
        "url": "https://www.swiftjournal.io/",
        "tag": "Journal",
        "initials": "SJ",
        "description": "Automated trade journal and copier for MT4 and MT5 accounts.",
    },
    {
        "name": "Momo India Screener",
        "url": "https://momoindiascreener.in/",
        "tag": "Screener",
        "logo": "assets/logos/momoindiascreener.png",
        "description": "Momentum screener ranking NSE stocks by Sharpe-based returns.",
    },
    {
        "name": "PaperTrade",
        "url": "https://papertrade.live/",
        "tag": "Practice",
        "initials": "PT",
        "description": "Paper-trading simulator to rehearse strategies with virtual money.",
    },
    {
        "name": "ScanX",
        "url": "https://scanx.trade/",
        "tag": "Screener",
        "logo": "assets/logos/scanx.png",
        "description": "Dhan's Indian stock screener with readymade screens and live market insights.",
    },
    {
        "name": "Punch",
        "url": "https://tech.punch.trade/",
        "tag": "Algo trading",
        "logo": "assets/logos/punch.png",
        "description": "Options and algo trading workspace from Market Pulse Securities.",
    },
    {
        "name": "OrderBlock",
        "url": "https://order-block.com/",
        "tag": "Order flow",
        "logo": "assets/logos/orderblock.svg",
        "description": "Live order blocks and liquidity ranked across Indian F&O stocks.",
    },
)


def main() -> None:
    theme.page_header(
        "Tool Directory",
        "The platforms and services we reach for across Indian capital markets, "
        "collected in one place.",
    )

    theme.section_header(
        "Platforms & services",
        f"{len(TOOLS)} external tools — screeners, research, journals, macro data "
        "and automation. Every card opens the vendor's site in a new tab.",
    )

    theme.tool_grid(TOOLS)

    st.caption(
        "These cards link to third-party sites; The Trading Dashboard is not "
        "affiliated with them."
    )


if __name__ == "__main__":
    main()
