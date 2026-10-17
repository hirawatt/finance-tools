"""Broker holdings import: detect the file, read it, resolve it, canonicalise it.

The public entry point is :func:`import_holdings`, which turns raw upload bytes
into a canonical, symbol-resolved, values-derived frame the analytics pages
already understand.

Built-in profiles cover the brokers this book actually uses — Zerodha, Groww,
Dhan and Angel One — and the generic profile plus a saved column mapping covers
everything else. Detection is by header content, so a renamed file still lands
on the right reader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import pandas as pd

from utils import holdings
from utils.brokers import angelone, dhan, generic, groww, zerodha
from utils.brokers.base import (
    TARGET_COLUMNS,
    BrokerProfile,
    find_alias_row,
    find_header_row,
    find_signature_row,
    guess_mapping,
    map_columns,
    parse,
    read_raw,
    slice_table,
)

#: Detection order matters: the earlier a profile is listed, the higher it ranks
#: when several signatures match, so the most specific broker sits first.
PROFILES = (zerodha.PROFILE, dhan.PROFILE, angelone.PROFILE, groww.PROFILE)

#: The last resort, used when nothing detects or the user picks it.
GENERIC = generic.PROFILE

ALL_PROFILES = PROFILES + (GENERIC,)
PROFILES_BY_NAME: Dict[str, BrokerProfile] = {profile.name: profile for profile in ALL_PROFILES}
PROFILE_NAMES = tuple(profile.name for profile in ALL_PROFILES)


def detect_profile(data: bytes, filename: str = "") -> Optional[BrokerProfile]:
    """The broker whose signature the file carries, or ``None`` if none does.

    Most tokens matched wins; a tie keeps the profile listed first in
    :data:`PROFILES`. A file with no signature at all is not claimed.
    """
    raw = read_raw(data, filename)
    best: Optional[BrokerProfile] = None
    for profile in PROFILES:
        if not profile.signature:
            continue
        if find_signature_row(raw, profile.signature) is not None:
            if best is None or len(profile.signature) > len(best.signature):
                best = profile
    return best


def preview_table(data: bytes, filename: str, profile: Optional[BrokerProfile] = None) -> pd.DataFrame:
    """The raw table with the broker's own column names — for a mapping screen."""
    raw = read_raw(data, filename)
    profile = profile or GENERIC
    header_row = find_signature_row(raw, profile.signature)
    if header_row is None:
        header_row = find_alias_row(raw, profile)
    if header_row is None:
        header_row = find_header_row(raw, profile.header_token)
    if header_row is None:
        header_row = find_header_row(raw, "isin")
    if header_row is None:
        return raw
    return slice_table(raw, header_row)


@dataclass
class BrokerImport:
    """Everything the import page needs to preview and confirm one file."""

    holdings: pd.DataFrame
    resolved: pd.DataFrame
    profile: str
    source: str
    detected: bool
    summary: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def core(self) -> pd.DataFrame:
        """The four-column frame the analytics pages read."""
        return holdings.to_core(self.holdings)


def import_holdings(
    data: bytes,
    filename: str,
    *,
    profile: Optional[BrokerProfile] = None,
    master: Optional[holdings.SymbolMaster] = None,
    aliases: Optional[Mapping[str, str]] = None,
    client: str = "",
    prices: Optional[Mapping[str, float]] = None,
) -> BrokerImport:
    """Read one broker file into a resolved, canonical holdings frame.

    ``profile`` overrides detection; ``master`` is the symbol master (an empty one
    leaves symbols merely normalised); ``prices`` values the holdings from the
    nightly snapshot instead of the broker's own probably-stale price.
    """
    warnings: List[str] = []
    detected = profile is None
    if profile is None:
        profile = detect_profile(data, filename) or GENERIC
        if profile is GENERIC:
            warnings.append(
                "Could not tell which broker this file came from — check the "
                "column mapping below."
            )

    try:
        mapped = parse(data, filename, profile)
    except ValueError as error:
        # No table at all: return an empty import with the reason, so the page
        # can explain it rather than blowing up.
        return BrokerImport(
            holdings=holdings.canonical(pd.DataFrame()),
            resolved=pd.DataFrame(),
            profile=profile.name,
            source=filename,
            detected=False,
            summary={status: 0 for status in holdings.MATCH_STATUSES},
            warnings=[str(error)],
        )
    if client:
        mapped["Client"] = client

    has_key = mapped.reindex(columns=["Symbol", "ISIN", "Company"]).notna().any().any()
    if not has_key:
        warnings.append(
            "No symbol, ISIN or company column was recognised in this file."
        )

    resolved = holdings.resolve(mapped, master or holdings.SymbolMaster(), aliases=aliases)
    derived = holdings.derive_values(resolved, prices)
    canonical = holdings.canonical(derived)

    unmatched = int(canonical["Symbol"].astype(str).str.strip().eq("").sum())
    if unmatched:
        warnings.append(f"{unmatched} row(s) have no symbol and were left out of the totals.")

    return BrokerImport(
        holdings=canonical,
        resolved=derived,
        profile=profile.name,
        source=filename,
        detected=detected and profile is not GENERIC,
        summary=holdings.match_summary(derived),
        warnings=warnings,
    )


__all__ = [
    "ALL_PROFILES",
    "BrokerImport",
    "BrokerProfile",
    "GENERIC",
    "PROFILES",
    "PROFILES_BY_NAME",
    "PROFILE_NAMES",
    "TARGET_COLUMNS",
    "detect_profile",
    "guess_mapping",
    "import_holdings",
    "map_columns",
    "parse",
    "preview_table",
    "read_raw",
]
