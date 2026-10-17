"""Dhan holdings export."""

from utils.brokers.base import BrokerProfile

PROFILE = BrokerProfile(
    name="Dhan",
    signature=("isin", "avg. cost"),
    columns={
        "Symbol": ("Trading Symbol", "Symbol"),
        "Company": ("Security Name", "Company Name", "Name"),
        "ISIN": ("ISIN",),
        "Average Price": ("Avg. Cost Price", "Avg Cost Price", "Average Price"),
        "Current Price": ("LTP", "Current Price", "Market Price"),
        "Total Quantity": ("Quantity", "Qty", "Net Quantity"),
    },
    export_url="https://web.dhan.co/",
    export_steps=(
        "Dhan web → Portfolio → Holdings → export the CSV/XLSX. Columns read "
        "Trading Symbol, Security Name, Avg. Cost Price and LTP."
    ),
)
