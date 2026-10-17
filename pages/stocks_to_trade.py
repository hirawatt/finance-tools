"""Idea Generation — screen the market for trade candidates."""

import streamlit as st

from utils import theme


def main():
    theme.page_header(
        "Idea Generation",
        "Shortlist trade candidates by the conditions that matter to you.",
    )

    trading_parameters = ["Liquidity", "Low Spreads", "High Volatility"]
    st.pills(
        "Conditions | Parameters",
        trading_parameters,
        selection_mode="multi",
        default=trading_parameters,
    )


if __name__ == "__main__":
    main()
