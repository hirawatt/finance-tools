import streamlit as st
import streamlit.components.v1 as components

website = st.secrets['credits']['website']
name = st.secrets['credits']['name']
buymeacoffee = st.secrets['credits']['buymeacoffee']

@st.cache_data()
def footer():
    with st.expander("Credits", expanded=True):
        st.markdown('<div style="text-align: center">Made with ☕️ by <a href="{}">{}</a></div>'.format(website, name), unsafe_allow_html=True)
        components.html(
            '{}'.format(buymeacoffee),
            height=80
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
