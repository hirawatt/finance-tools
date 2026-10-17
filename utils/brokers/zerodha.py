"""Zerodha Console holdings — the export this app started with.

The Console XLSX carries a client block and a summary before the holdings table,
and splits quantity across available/long-term/pledged buckets. The profile
records both, which is why the old ``header=22`` hard-coding is gone.
"""

from utils.brokers.base import BrokerProfile

PROFILE = BrokerProfile(
    name="Zerodha",
    signature=("quantity available", "previous closing price"),
    columns={
        "Symbol": ("Symbol",),
        "ISIN": ("ISIN",),
        "Sector": ("Sector",),
        "Average Price": ("Average Price",),
        "Current Price": ("Previous Closing Price",),
        "Unrealized P&L": ("Unrealized P&L",),
    },
    quantity_sources=(
        "Quantity Available",
        "Quantity Discrepant",
        "Quantity Long Term",
        "Quantity Pledged (Margin)",
        "Quantity Pledged (Loan)",
    ),
    export_url="https://console.zerodha.com/portfolio/holdings/",
    export_steps=(
        "Zerodha Console → Portfolio → Holdings → download the XLSX. Use Family "
        "Portfolio for a joint/family book."
    ),
)
