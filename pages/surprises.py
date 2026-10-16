import streamlit as st


def main():
    st.title("🚦 Due Diligence")
    st.caption(
        "Surfaces worth a closer look before you trade — unusual pricing and "
        "volume that can signal either an opportunity or a trap."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.subheader("Options Pricing Mismatch")
    c2.subheader("Unusual Moves in Pairs")
    c3.subheader(":whale: Unusual Volume in Stocks")
    c4.subheader(":whale2: Unusual Volume in Options")


if __name__ == "__main__":
    main()
