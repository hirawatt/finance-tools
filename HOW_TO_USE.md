# Portfolio Analyzer

## Requirements for a Portfolio

- [ ] Reduce Risk
- [ ] Maximize Returns

### Reduce Risk Measurement

- [ ] 

### Maximize Returns Measurement

- [ ]

## Code Snippets

```python
def color_positive_green(val):
    #Takes a scalar and returns a string with
    #the css property `'color: green'` for positive
    #strings, black otherwise.
    if val > 0:
        color = 'green'
    else:
        color = 'black'
    return 'color: %s' % color  
#st.dataframe(df1.style.applymap(color_positive_green))
#st.dataframe(df1.style.set_properties(**{'background-color': 'white', 'color': 'green'}))
#st.dataframe(df1[['Symbol', 'Sector', 'Quantity Available', 'Average Price', 'Previous Closing Price', 'Unrealized P&L', 'Unrealized P&L Pct.']]) # [0, 2, 3, 8, 9,10,11]
```