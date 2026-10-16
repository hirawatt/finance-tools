import streamlit as st


def main():
    st.title("💡 Idea Generation")
    st.caption("Shortlist trade candidates by the conditions that matter to you.")

    trading_parameters = ["Liquidity", "Low Spreads", "High Volatility"]
    st.multiselect("Conditions | Parameters", trading_parameters, default=trading_parameters)


if __name__ == "__main__":
    main()
