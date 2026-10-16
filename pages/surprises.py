"""Due Diligence — screens for surprises and unusual market activity."""

import streamlit as st

from utils import theme

# The cross-market checks this desk will run, in display order.
SCREENS = (
    ("📐", "Options Pricing Mismatch", "Put-call parity breaks that shouldn't be there."),
    ("🧩", "Unusual Moves in Pairs", "Twin stocks drifting apart beyond their usual spread."),
    ("🐋", "Unusual Volume in Stocks", "Cash-market prints far above the recent average."),
    ("🐳", "Unusual Volume in Options", "Open-interest and volume surges in the derivatives book."),
)


def main():
    theme.page_header(
        "Due Diligence",
        "Surfaces worth a closer look before you trade — unusual pricing and "
        "volume that can signal either an opportunity or a trap.",
    )

    for index, (column, (icon, title, body)) in enumerate(zip(st.columns(4), SCREENS)):
        with column, st.container(border=True, key=f"td-card-screen-{index}"):
            st.markdown(
                '<div class="td-card">'
                f'<div class="td-card__icon">{icon}</div>'
                f'<div class="td-card__title">{title}</div>'
                f'<p class="td-card__body">{body}</p>'
                "</div>",
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
