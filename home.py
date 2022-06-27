import streamlit as st
import pandas as pd
from pathlib import Path

from annotated_text import annotated_text

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
    ## Glossary
    |Meaning|Emoji|
    |:-:|:-:|
    |Build in Progress|🔮|
    |Complete|🧰|

    """
    )
    
    annotated_text(
        "This ",
        ("is", "verb"),
        " some ",
        ("annotated", "adj"),
        ("text", "noun"),
        " for those of "
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