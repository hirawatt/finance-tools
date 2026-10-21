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
    st.session_state.setdefault("pct", 0.0)
    percent = c2.number_input("Percentage change (%)", step=0.5, key="pct")

    # Preset buttons move the percentage input; a horizontal container keeps the
    # row responsive instead of a fixed two-column grid of buttons.
    with st.container(horizontal=True):
        for preset in STEPS:
            st.button(f"{preset:+g}%", on_click=set_percent, args=(preset,))

    result = apply_change(value, percent)
    change = result - value
    theme.metric_row(
        (
            ("New value", f"{result:,.2f}"),
            (
                "Change",
                f"{change:+,.2f}",
                # A flat move must not show a green up-arrow (see st.metric).
                0 if not percent else f"{percent:+.2f}%",
            ),
        )
    )


if __name__ == "__main__":
    main()
