"""Due Diligence — screens for surprises and unusual market activity."""

import streamlit as st

from utils import theme

# The cross-market checks this desk will run, in display order. The first item
# is a Material Symbols name (see utils/theme.py).
SCREENS = (
    ("compare_arrows", "Options pricing mismatch", "Put-call parity breaks that shouldn't be there."),
    ("difference", "Unusual moves in pairs", "Twin stocks drifting apart beyond their usual spread."),
    ("monitoring", "Unusual volume in stocks", "Cash-market prints far above the recent average."),
    ("candlestick_chart", "Unusual volume in options", "Open-interest and volume surges in the derivatives book."),
)


def main():
    theme.page_header(
        "Due Diligence",
        "Surfaces worth a closer look before you trade — unusual pricing and "
        "volume that can signal either an opportunity or a trap.",
    )

    for index, (column, (icon, title, body)) in enumerate(zip(st.columns(4), SCREENS)):
        with column:
            theme.card(icon, title, body, key=f"td-card-screen-{index}")


if __name__ == "__main__":
    main()
