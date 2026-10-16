"""Small-cap stock screener."""

import streamlit as st
import pandas as pd


@st.cache_data
def load_companies() -> pd.DataFrame:
    """The added company master list. Cached so the CSV is parsed once per
    process instead of on every rerun."""
    return pd.read_csv('./data/all-companies-list.csv', dtype={'BSE Code': str})


def main() -> None:
    st.title("❄️ Stock Search")
    st.caption("Screen small-caps by price and see how a candidate set fits your plan.")

    with st.sidebar:
        st.subheader("Screener settings")
        with st.form("stock_screen_info"):
            no_of_stocks = st.number_input(
                "No. of stocks", value=21, min_value=1, max_value=100
            )
            min_investment = st.number_input(
                "Min. investment (₹)", value=28106, min_value=1, max_value=100000
            )
            max_portfolio_allocation = st.number_input(
                "Max. allocation per stock (%)", value=10, min_value=1, max_value=100
            )
            universe = st.multiselect(
                "Universe", ["Large Cap", "Mid Cap", "Small Cap"], default=["Small Cap"]
            )
            submitted = st.form_submit_button("Submit")
        if submitted:
            st.write(
                "No. of stocks", no_of_stocks, "· universe", universe,
                "· min. investment", min_investment,
            )

    avg_investment_value = round(min_investment / no_of_stocks, 2)
    max_stock_price = round(max_portfolio_allocation * min_investment / 100, 2)
    c1, c2 = st.columns(2)
    c1.metric("Average investment value (₹)", f"{avg_investment_value:,.2f}")
    c2.metric("Max. stock price (₹)", f"{max_stock_price:,.2f}")

    companies = load_companies().iloc[:, [0, 1, 2, 3, 4]]

    # The master list is ordered by market cap, so its tail is the small-cap
    # universe used by this screen.
    small_cap = companies[251:].rename(columns={"Current Price": "Price"})
    bse_only = small_cap[small_cap["NSE Code"].isna()]
    nse_only = small_cap[small_cap["BSE Code"].isna()]
    dual_listed = small_cap[small_cap["NSE Code"].notna() & small_cap["BSE Code"].notna()]

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Small-cap companies", f"{len(small_cap):,}")
    a2.metric("BSE only", f"{len(bse_only):,}")
    a3.metric("NSE only", f"{len(nse_only):,}")
    a4.metric("BSE and NSE", f"{len(dual_listed):,}")

    min_stock_price = st.number_input(
        "Min. stock price (₹)", value=25, min_value=0, max_value=100
    )
    in_budget = (small_cap["Price"] <= max_stock_price) & (small_cap["Price"] >= min_stock_price)
    stock_search = small_cap[in_budget]
    held = st.multiselect("Stocks already in your portfolio", stock_search["Name"])

    candidates = stock_search[~stock_search["Name"].isin(held)]
    st.subheader("Candidates")
    st.caption(
        f"{len(candidates):,} of {len(stock_search):,} stocks in the price band, "
        "excluding the ones you already hold."
    )
    st.dataframe(candidates, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
