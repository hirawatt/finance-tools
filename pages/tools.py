"""Everyday trading calculators."""

import streamlit as st

from utils import theme

# Percentage steps offered as preset buttons, in display order.
STEPS = (5.0, 3.0, 2.0, -2.0, -3.0, -5.0)


def apply_change(value: float, percent: float) -> float:
    """Return ``value`` moved by ``percent`` percent."""
    return value * (1 + percent / 100)


def set_percent(percent: float) -> None:
    """Button callback: write the chosen percentage into the input widget."""
    st.session_state.pct = percent


def main() -> None:
    theme.page_header("Tools", "Quick calculators for everyday trading maths.")

    theme.section_header(
        "Percentage up/down",
        "Enter a value and a percentage move to see the resulting value.",
    )

    c1, c2 = st.columns(2)
    value = c1.number_input("Value", value=100.0, step=1.0)
    if "pct" not in st.session_state:
        st.session_state.pct = 0.0
    percent = c2.number_input("Percentage change (%)", step=0.5, key="pct")

    col1, col2 = st.columns(2)
    for column, percents in ((col1, STEPS[:3]), (col2, STEPS[3:])):
        for preset in percents:
            column.button(f"{preset:+g}%", on_click=set_percent, args=(preset,))

    result = apply_change(value, percent)
    r1, r2 = st.columns(2)
    r1.metric("New value", f"{result:,.2f}")
    r2.metric("Change", f"{result - value:+,.2f}")


if __name__ == "__main__":
    main()
