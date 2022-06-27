import streamlit as st

def main():
    st.subheader("Surprises")
    c1, c2, c3, c4 = st.columns(4)
    c1.subheader("Options Pricing Mismatch")
    c2.subheader("Unusual Moves in Pairs")
    c3.subheader(":whale: Unusual Volume in Stocks")
    c4.subheader(":whale2: Unusual Volume in Options")


if __name__ == "__main__":
    st.set_page_config(
        "Surprises",
        "🕴️",
        initial_sidebar_state="expanded",
        layout="wide",
    )
    main()