import streamlit as st
import pandas as pd
from pathlib import Path

def main() -> None:
    st.write("# Welcome to The Trading Dashboard")

    st.markdown(
        '''
        - 🚀 Co-Pilot
        - 💡 Idea Generation
        - 🚦 Due Diligence
        '''
    )

    info = pd.read_csv('./data/info.csv')
    #st.dataframe(info)

    st.write(Path("./data/DATA.md").read_text())
    st.markdown(
    """
    ## Data Sources

    ||||
    |:-:|:-:|:-:|
    |NSE Nifty Small Cap 100| [Nifty Small Cap 100](https://www1.nseindia.com/content/indices/ind_niftysmallcap100list.csv)||
    |All Companies List| [Screener Screens](https://www.screener.in/screens/722948/all-companies-list/)||
    
    ## Glossary

    |Emoji|Meaning|
    |:-:|:-:|
    |✅|FIXED|
    |🚀|ADDED|
    |👍|IMPROVED|
    |🧪|EXPERIMENT|

    """
    )
    
if __name__ == "__main__":
    st.set_page_config(
        "The Trading Dashboard by Hirawat",
        "🕴️",
        initial_sidebar_state="expanded",
        layout="wide",
        menu_items={
            "Get Help": "https://github.com/hirawatt/finance-tools",
            "Report a bug": "https://github.com/hirawatt/finance-tools/issues",
            "About": "# This is an *extremely* cool app!",
            },
    )
    main()