import streamlit as st

def main():
    trading_parameters = ["Liquidity", "Low Spreads", "High Volatility"]
    st.multiselect("Conditions | Parameters", trading_parameters, default=trading_parameters)

if __name__ == "__main__":
    st.set_page_config(
        "Stocks To Trade",
        "🕴️",
        initial_sidebar_state="expanded",
        layout="wide",
    )
    main()