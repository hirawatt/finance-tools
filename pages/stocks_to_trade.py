import streamlit as st


def main():
    trading_parameters = ["Liquidity", "Low Spreads", "High Volatility"]
    st.multiselect("Conditions | Parameters", trading_parameters, default=trading_parameters)


if __name__ == "__main__":
    main()