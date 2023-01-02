import streamlit as st
import pandas as pd
import numpy as np

raw_data = pd.read_csv('./data/all-companies-list.csv', dtype={'BSE Code': str})

# Combination Sum
from itertools import combinations

@st.cache
def find_combos(arr, no_of_stocks):
    combos = list(combinations(arr, no_of_stocks))
    combo_sums = []
    for combo in combos:
        combo_sums.append(sum(combo))
    return combo_sums

def main():
    st.sidebar.subheader("Fund Stock Screener")
    with st.sidebar.form("stock_screen_info"):
        st.write("Stock Screen Info")
        no_of_stocks = st.number_input("No. of Stocks", value=21, min_value=1, max_value=100)
        min_investment = st.number_input("Min. Investment", value=28106, min_value=1, max_value=100000)
        max_portfolio_allocation = st.number_input("Maximum Portfolio Allocation for a single stock", value=10, min_value=1, max_value=100)
        universe = st.multiselect("Universe", ["Large Cap", "Mid Cap", "Small Cap"], default=["Small Cap"])

        submitted = st.form_submit_button("Submit")
        if submitted:
            st.write("No. of Stocks", no_of_stocks, "universe", universe, "Min. Investment", min_investment)

    avg_investment_value = round(min_investment/no_of_stocks, 2)
    max_stock_price = round(max_portfolio_allocation*min_investment/100, 2)
    c1, c2 = st.columns(2)
    c1.metric("Average Investment Value", avg_investment_value)
    c2.metric("Max. Stock Price", max_stock_price)

    # Stock Search Base Dataframe
    df = raw_data.iloc[:, [0, 1, 2, 3, 4]]

    ## Small-Cap Filter
    #small_cap = df[251:].count()
    small_cap = df[251:].rename(columns={
                'Current Price':'Price'}
                )
    nse_bse_small_cap = small_cap.dropna().count()
    
    bse_only_list = small_cap["NSE Code"].isnull()
    bse_only = small_cap[bse_only_list]
    nse_only_list = small_cap["BSE Code"].isnull()
    nse_only = small_cap[nse_only_list]

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("No. of Small Cap Companies", str(small_cap.count()[3]))
    a2.metric("No. of BSE Only Companies", str(bse_only.count()[3]))
    a3.metric("No. of NSE Only Companies", str(nse_only.count()[3]))
    a4.metric("No. of BSE/NSE Companies", str(nse_bse_small_cap[0]))

    min_stock_price = st.number_input("Min. Stock Price", value=25, min_value=0, max_value=100)
    base_df = ((small_cap.Price <= max_stock_price) & (small_cap.Price >= min_stock_price))
    stock_search = small_cap[base_df]
    stocks_known = st.multiselect("Stocks known in Portfolio", stock_search.Name)

    # Stock Search Base Dataframe
    st.write()
    updated_price = []
    """
    for i in stock_search.Price:
        if i > avg_investment_value:
            updated_price.append(i)
        elif i < avg_investment_value:
            updated_price.append((round(avg_investment_value)/round(i)) * i)
    
    stock_search = stock_search.assign(updated_price = updated_price)
    stock_search = stock_search.assign(no_of_shares = round(stock_search.updated_price/stock_search.Price))
    updated_no_of_stocks = no_of_stocks - len(stocks_known)
    st.write(stock_search)
    st.write("Base DF to iterate", small_cap[base_df].Price.count(), "Stocks for", updated_no_of_stocks, "more in Portfolio")
    st.subheader("Stock Search")


    ans = find_combos(stock_search.updated_price, updated_no_of_stocks)
    # print all combinations stored in ans
    st.write(ans)
    """



if __name__ == "__main__":
    main()