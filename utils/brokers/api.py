"""Consented broker APIs — the live-holdings path, for a self-hosted deployment.

A broker file export is the right default: nothing to register, nothing to store,
and it works on a public instance. The API path is for the operator who runs the
dashboard on their own host with auth in front of it, where a client can authorise
once and their holdings refresh on a schedule.

Three rules shape this module:

* **The client authorises, we never hold their password.** Each broker issues an
  access token through its own OAuth (or TOTP) flow, and we only ever store that
  token — server-side, never in the browser. Nothing here asks for a credential.
* **No scraping.** Only documented endpoints, and only with a token the account
  holder granted.
* **Nothing is guessed.** Response field names differ per broker and drift, so
  records are normalised through per-provider alias lists rather than one assumed
  shape. Where a broker's field names have not been confirmed against a live
  account, the provider says so in :attr:`ApiProvider.note`.

This module is deliberately not wired into the UI yet: it needs an authenticated
deployment and a token store (the intended PocketBase backend) to be useful, and
advertising a button that cannot work would be worse than shipping none.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd


class NotConfigured(RuntimeError):
    """Raised when an API call is attempted without a token to make it with."""


@dataclass(frozen=True)
class ApiProvider:
    """Everything needed to call one broker's holdings endpoint."""

    name: str
    docs: str
    #: How the account holder grants access: ``oauth`` or ``key+totp``.
    auth_kind: str
    holdings_url: str
    method: str = "GET"
    #: How long an access token lasts; brokers require a daily re-authorisation.
    token_ttl_hours: int = 24
    #: ``{token}`` and ``{api_key}`` placeholders for the auth header value.
    auth_header: str = "Authorization"
    token_format: str = "Bearer {token}"
    #: Header the app key travels in, when it is not inside the token string.
    api_key_header: str = ""
    #: Envelope keys to find the list of holdings inside the payload.
    payload_paths: Tuple[Tuple[str, ...], ...] = (("data",), ("holdings",))
    #: Canonical target → response keys, most likely first.
    record_aliases: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    note: str = ""

    def headers(self, token: str, api_key: str = "") -> Dict[str, str]:
        """The request headers for a call with ``token`` (and ``api_key``)."""
        headers = {
            self.auth_header: self.token_format.format(token=token, api_key=api_key)
        }
        if self.api_key_header and api_key:
            headers[self.api_key_header] = api_key
        return headers

    def normalise(self, records: Sequence[Mapping]) -> pd.DataFrame:
        """Map broker records into the canonical target columns."""
        rows: List[Dict[str, object]] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            row: Dict[str, object] = {}
            for target, keys in self.record_aliases.items():
                for key in keys:
                    if record.get(key) not in (None, ""):
                        row[target] = record[key]
                        break
            if row:
                rows.append(row)
        frame = pd.DataFrame(rows, columns=list(self.record_aliases))
        frame["Broker"] = self.name
        return frame


#: Canonical field → the response keys seen across providers. Kept in one place
#: so a new broker usually needs only a name, a URL and an auth mode.
COMMON_RECORD_ALIASES: Mapping[str, Tuple[str, ...]] = {
    "Symbol": ("tradingsymbol", "tradingSymbol", "symbol", "scrip"),
    "ISIN": ("isin", "ISIN", "isinCode"),
    "Company": ("company_name", "securityName", "security_name", "companyName", "name"),
    "Total Quantity": ("quantity", "totalQty", "netQty", "qty", "holdingsQty"),
    "Average Price": ("average_price", "avgCostPrice", "averageprice", "avgPrice", "buyAvg"),
    "Current Price": ("last_price", "lastTradedPrice", "ltp", "lastPrice", "closePrice"),
    "Unrealized P&L": ("pnl", "unrealisedPnl", "unrealizedPnl", "profitAndLoss"),
}


def _aliases(**overrides) -> Mapping[str, Tuple[str, ...]]:
    """The common aliases with per-broker keys put first where they differ."""
    merged = {target: tuple(keys) for target, keys in COMMON_RECORD_ALIASES.items()}
    for target, keys in overrides.items():
        merged[target] = tuple(keys) + merged.get(target, ())
    return merged


PROVIDERS: Tuple[ApiProvider, ...] = (
    ApiProvider(
        name="Zerodha",
        docs="https://kite.trade/docs/connect/v3/portfolio/",
        auth_kind="oauth",
        holdings_url="https://api.kite.trade/portfolio/holdings",
        auth_header="Authorization",
        token_format="token {api_key}:{token}",
        payload_paths=(("data",),),
        record_aliases=_aliases(),
        note="Kite Connect is a paid app; access tokens expire daily and the client logs in each day.",
    ),
    ApiProvider(
        name="Upstox",
        docs="https://upstox.com/developer/api-documentation/get-holdings/",
        auth_kind="oauth",
        holdings_url="https://api.upstox.com/v2/portfolio/long-term-holdings",
        payload_paths=(("data",),),
        record_aliases=_aliases(),
        note="OAuth 2.0; the token expires daily.",
    ),
    ApiProvider(
        name="Dhan",
        docs="https://dhanhq.co/docs/v2/portfolio/",
        auth_kind="token",
        holdings_url="https://api.dhan.co/v2/holdings",
        auth_header="access-token",
        token_format="{token}",
        payload_paths=(("data",),),
        record_aliases=_aliases(),
        note="Field names to confirm against a live account before enabling.",
    ),
    ApiProvider(
        name="Angel One",
        docs="https://smartapi.angelbroking.com/docs",
        auth_kind="key+totp",
        holdings_url=(
            "https://apiconnect.angelbroking.com/rest/secure/angelbroking/portfolio/v1/getAllHolding"
        ),
        method="POST",
        payload_paths=(("data", "holdings"), ("data",), ("holdings",)),
        record_aliases=_aliases(),
        note="SmartAPI logs in with an API key and a TOTP each day. Field names to confirm.",
    ),
)

PROVIDERS_BY_NAME: Dict[str, ApiProvider] = {provider.name: provider for provider in PROVIDERS}


def records_from_payload(provider: ApiProvider, payload: object) -> List[Mapping]:
    """Find the list of holdings inside a broker's response envelope."""
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, Mapping)]
    for path in provider.payload_paths:
        node: object = payload
        for key in path:
            if not isinstance(node, Mapping):
                node = None
                break
            node = node.get(key)
        if isinstance(node, list):
            return [record for record in node if isinstance(record, Mapping)]
    return []


def build_request(
    provider: ApiProvider, token: str, api_key: str = ""
) -> Tuple[str, Dict[str, str], Optional[bytes]]:
    """The (url, headers, body) a call would use — separated so it is testable."""
    if not token:
        raise NotConfigured(f"{provider.name} needs an access token.")
    headers = provider.headers(token, api_key)
    body = b"{}" if provider.method == "POST" else None
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
    return provider.holdings_url, headers, body


def fetch_holdings(
    provider: ApiProvider,
    token: str,
    *,
    api_key: str = "",
    timeout: int = 15,
) -> pd.DataFrame:
    """Fetch and normalise one broker's holdings. Network; not used in tests.

    The caller owns the token (client-side, server-stored); this never sees a
    password and never writes the token anywhere.
    """
    url, headers, body = build_request(provider, token, api_key)
    request = urllib.request.Request(url, data=body, headers=headers, method=provider.method)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - documented brokers only
        payload = json.loads(response.read().decode("utf-8"))
    return provider.normalise(records_from_payload(provider, payload))
