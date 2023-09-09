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

    st.markdown(
        '''
        - 🚀 Co-Pilot
        - 💡 Idea Generation
        - 🚦 Due Diligence
        '''
    )

    info = pd.read_csv('./data/info.csv')
    #st.dataframe(info)

    st.write(Path("DATA.md").read_text())

    
if __name__ == "__main__":
    main()