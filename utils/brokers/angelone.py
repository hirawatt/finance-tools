"""Angel One holdings export."""

from utils.brokers.base import BrokerProfile

PROFILE = BrokerProfile(
    name="Angel One",
    signature=("instrument", "avg. price"),
    columns={
        "Symbol": ("Symbol", "Instrument", "Trading Symbol", "Scrip"),
        "Company": ("Company Name", "Security Name", "Name"),
        "ISIN": ("ISIN",),
        "Average Price": ("Avg. Price", "Avg Price", "Average Price", "Buy Avg"),
        "Current Price": ("LTP", "Current Price", "Market Price"),
        "Total Quantity": ("Qty", "Quantity"),
    },
    export_url="https://trade.angelone.in/",
    export_steps=(
        "Angel One → Portfolio → Holdings → download the statement. Columns read "
        "Instrument, Qty, Avg. price and LTP."
    ),
)
