import streamlit as st
import streamlit.components.v1 as components

@st.cache(suppress_st_warning=True)
def footer():
    with st.expander("Credits", expanded=True):
        st.success('Created by VH')
        components.html(
        """
        <script type="text/javascript" src="https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js" data-name="bmc-button" data-slug="hirawat" data-color="#FFDD00" data-emoji="☕"  data-font="Poppins" data-text="Buy me a coffee" data-outline-color="#000000" data-font-color="#000000" data-coffee-color="#ffffff" ></script>
        """,
        height=100
        )

def main():
    footer()

if __name__ == "__main__":
    st.set_page_config(
        "About",
        "🕴️",
        initial_sidebar_state="expanded",
        layout="wide",
    )
    main()
