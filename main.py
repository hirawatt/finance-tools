import streamlit as st
import pandas as pd
from pathlib import Path

# streamlit
st.set_page_config(
    'The Trading Dashboard by Hirawat',
    '🕴️',
    layout='wide',
    initial_sidebar_state='expanded',
    menu_items={
        "Get Help": "https://github.com/hirawatt/finance-tools",
        "About": "Finance tools for Capital Markets",
        "Report a bug": "https://github.com/hirawatt/finance-tools/issues",
    },
)

def main() -> None:
    st.write("# Welcome to The Trading Dashboard")

    st.page_link("pages/3_💰_portfolio_analysis.py", label="🚀 Co-Pilot", use_container_width=True)
    st.page_link("pages/1_📈_stocks_to_trade.py", label="💡 Idea Generation", use_container_width=True)
    st.page_link("pages/4_🤯_surprises.py", label="🚦 Due Diligence", use_container_width=True)
    st.markdown("---") # Add a separator

    info = pd.read_csv('./data/info.csv')
    #st.dataframe(info)

    st.write(Path("DATA.md").read_text())

    
if __name__ == "__main__":
    main()