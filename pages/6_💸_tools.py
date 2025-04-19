import streamlit as st

st.set_page_config(
    "Tools",
    "🕴️",
    initial_sidebar_state="expanded",
    layout="wide",
)
tab1, tab2 = st.tabs(["Percentage Up Down Calc", "News Sentiment"])

with tab1:
    c1, c2, c3 = st.columns(3)
    # Pre-Defined Percentage Changes
    p5 = c1.button('+5%', key='p5')
    p3 = c1.button('+3%', key='p3')
    p2 = c1.button('+2%', key='p2')
    m5 = c2.button('-5%', key='m5')
    m3 = c2.button('-3%', key='m3')
    m2 = c2.button('-2%', key='m2')
    # Custom Percentage Changes
    pct = c3.number_input('Custom Percentage Change', value=0.0, step=0.01, key='pct')

    def pct_change(number: float) -> float:
        """Calculate the percentage change of a number

        Args:
            number (float): The number to calculate the percentage change of

        Returns:
            float: The percentage change of the number
        """
        if p5:
            number = number*1.05
        elif p3:
            number = number*1.03
        elif p2:
            number = number*1.02
        elif m5:
            number = number*0.95
        elif m3:
            number = number*0.97
        elif m2:
            number = number*0.98
        else:
            number = number*(1+pct/100)
        return number

def main() -> None:
    with tab1:
        st.subheader("Percentage Up/Down")

        # Set Session state with Input Number
        if 'key' not in st.session_state:
            number = st.number_input("Enter a number:", value=100)
            st.session_state.key = number

        c1, c2 = st.columns(2)
        # Set Session state to store Original Input Number
        if 'number' not in st.session_state:
            st.session_state.number = st.session_state.key
        c1.metric("Starting number:", st.session_state.number)
        number = st.session_state.key
        st.session_state.key = pct_change(number)
        net_change = (st.session_state.number - st.session_state.key)/st.session_state.number * 100
        c2.metric("The net change is:", round(st.session_state.key, 2), delta=round(net_change, 2))

#     with tab2:
#         st.subheader("News Sentiment Analysis")
#         a1, a2 = st.columns(2)
#         input = a1.text_input(
#             "Enter News Headline",
#             value="Housing demand momentum to continue despite rising prices and interest rates: CRISIL",
#         )
#         output = news_sentiment(input)
#         a2.metric("Sentiment", value=output[0]["label"], delta=output[0]["score"])

# import transformers as tfmr

# @st.cache_resource
# def news_sentiment(input: str) -> list:
#     # Allocate a pipeline for sentiment-analysis
#     classifier = tfmr.pipeline("sentiment-analysis")
#     output = classifier(input)
#     return output
    

if __name__ == "__main__":
    main()