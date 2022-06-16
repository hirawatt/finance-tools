import streamlit as st
import pandas as pd

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

    df = pd.read_excel('./data/holdings-sample.xlsx', header=22, usecols="B:L")
    st.write(df)

if __name__ == "__main__":
    st.set_page_config(
        "The Trading Dashboard by Hirawat",
        "🕴️",
        initial_sidebar_state="expanded",
        layout="wide",
    )
    main()