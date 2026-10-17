"""Groww holdings export."""

from utils.brokers.base import BrokerProfile

PROFILE = BrokerProfile(
    name="Groww",
    signature=("isin", "average"),
    columns={
        "Company": ("Company Name", "Stock Name", "Name"),
        "Symbol": ("NSE Symbol", "Trading Symbol", "Stock Symbol", "Symbol"),
        "ISIN": ("ISIN",),
        "Average Price": ("Average buy price", "Average Price", "Avg Buy Price"),
        "Current Price": ("Current Price", "Closing Price", "LTP", "Market Price"),
        "Total Quantity": ("Quantity", "Qty", "Units"),
    },
    export_url="https://groww.in/",
    export_steps=(
        "Groww → Stocks → Holdings → download the statement (XLSX/CSV). The "
        "export carries the ISIN, which is what we resolve the symbol from."
    ),
)
