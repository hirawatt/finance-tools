"""NSE surveillance lists (ASM / GSM) monitoring.

Fetches NSE's Additional Surveillance Measure (ASM) and Graded Surveillance
Measure (GSM) lists and checks portfolio holdings against them. Parsing and
matching are pure; only :func:`fetch_surveillance` touches the network.

NSE occasionally gates these endpoints behind a session cookie, so a failed
first attempt is retried once after warming up cookies from the homepage.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Iterable, Optional

import pandas as pd

ASM_URL = "https://www.nseindia.com/api/reportASM"
GSM_URL = "https://www.nseindia.com/api/reportGSM"
NSE_HOME = "https://www.nseindia.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

SURVEILLANCE_COLUMNS = ["Symbol", "Company", "List", "Stage", "Code", "Updated"]


def _clean_symbol(value) -> str:
    return str(value or "").strip().upper()


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=SURVEILLANCE_COLUMNS)


def _asm_row(record: dict, term: str) -> dict:
    return {
        "Symbol": _clean_symbol(record.get("symbol")),
        "Company": record.get("companyName"),
        "List": f"ASM · {term}",
        "Stage": record.get("asmSurvIndicator") or record.get("survDesc"),
        "Code": record.get("survCode"),
        "Updated": record.get("asmTime"),
    }


def parse_asm(payload) -> pd.DataFrame:
    """Parse an ASM API payload into a normalised frame.

    Accepts the current ``{"longterm": {...}, "shortterm": {...}}`` shape and,
    defensively, a plain list of records.
    """
    rows = []
    if isinstance(payload, dict):
        for term, key in (("Long Term", "longterm"), ("Short Term", "shortterm")):
            section = payload.get(key)
            records = section.get("data") if isinstance(section, dict) else section
            for record in records or []:
                rows.append(_asm_row(record, term))
    elif isinstance(payload, list):
        for record in payload:
            rows.append(_asm_row(record, record.get("asmSurvIndicator") or "ASM"))

    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows, columns=SURVEILLANCE_COLUMNS)


def parse_gsm(payload) -> pd.DataFrame:
    """Parse a GSM API payload (a list of records) into a normalised frame."""
    rows = []
    for record in payload or []:
        stage = record.get("gsmStage")
        rows.append(
            {
                "Symbol": _clean_symbol(record.get("symbol")),
                "Company": record.get("companyName"),
                "List": "GSM",
                "Stage": f"Stage {stage}" if stage not in (None, "") else record.get("survDesc"),
                "Code": record.get("survCode"),
                "Updated": record.get("gsmTime"),
            }
        )

    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows, columns=SURVEILLANCE_COLUMNS)


def _get_json(url: str, timeout: int, cookie_jar) -> object:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    request = urllib.request.Request(url, headers=_HEADERS)
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _warm_up(cookie_jar, timeout: int) -> None:
    """Visit the NSE homepage to collect any session cookies the API needs."""
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        opener.open(urllib.request.Request(NSE_HOME, headers=_HEADERS), timeout=timeout).read()
    except Exception:
        pass


def fetch_surveillance(timeout: int = 25) -> pd.DataFrame:
    """Fetch and normalise the current ASM and GSM lists from NSE."""
    import http.cookiejar

    jar = http.cookiejar.CookieJar()

    def _load() -> pd.DataFrame:
        asm = parse_asm(_get_json(ASM_URL, timeout, jar))
        gsm = parse_gsm(_get_json(GSM_URL, timeout, jar))
        return pd.concat([asm, gsm], ignore_index=True)

    try:
        combined = _load()
    except Exception:
        _warm_up(jar, timeout)
        combined = _load()

    return combined[combined["Symbol"] != ""].reset_index(drop=True)


def check_symbols(symbols: Iterable[str], surveillance: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Rows of ``surveillance`` whose symbol is in ``symbols`` (case-insensitive)."""
    if surveillance is None or surveillance.empty:
        return _empty_frame()

    wanted = {_clean_symbol(s) for s in symbols if _clean_symbol(s)}
    matched = surveillance[surveillance["Symbol"].isin(wanted)]
    return matched.sort_values(["Symbol", "List"]).reset_index(drop=True)
