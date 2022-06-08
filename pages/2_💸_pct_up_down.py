import streamlit as st

# Pre-Defined Percentage Changes
c1, c2 = st.columns(2)
p5 = c1.button('+5%', key='p5')
p3 = c1.button('+3%', key='p3')
p2 = c1.button('+2%', key='p2')
m5 = c2.button('-5%', key='m5')
m3 = c2.button('-3%', key='m3')
m2 = c2.button('-2%', key='m2')

# Custom Percentage Changes
pct = st.number_input('Percentage', value=0.0, step=0.01, key='pct')

st.title("Percentage Up/Down")


# Set Session state with Input Number
if 'key' not in st.session_state:
    number = st.number_input("Enter a number:", value=100)
    st.session_state.key = number

# Set Session state to store Original Input Number
if 'number' not in st.session_state:
    st.session_state.number = st.session_state.key

def main():
    st.write("Starting number:", st.session_state.number)
    number = st.session_state.key
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
    st.session_state.key = number
    st.write("The percentage of the number is:", number)

if __name__ == "__main__":
    main()