"""The fallback profile: any spreadsheet with a recognisable symbol header.

It never auto-detects (an empty signature), so it only runs when the user picks
it or nothing else matched — and then the import page asks the user to confirm
the column mapping, which can be saved as a reusable profile.
"""

from utils.brokers.base import BrokerProfile

PROFILE = BrokerProfile(
    name="Generic",
    signature=(),
    columns={},
    header_token="symbol",
    notes="Any CSV/XLSX with a symbol, ISIN or company column.",
)
