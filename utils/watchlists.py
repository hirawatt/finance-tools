"""Reading the curated watchlists in ``indices/``.

A watchlist is a CSV of NSE symbols: one row for most lists, but long ones wrap
onto further rows, and a few files (``iAll``, ``tSummer``) name *other*
watchlists instead of symbols. Reading a single row would silently drop the
wrapped names and turn a meta-watchlist into fake tickers such as ``IAC``, so
this module reads every row and expands a token that matches another
watchlist's file name into that watchlist's symbols.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

# Kept as a type alias so callers can talk about one resolved list.
Watchlist = Tuple[str, ...]


def _read_symbols(path: Path) -> List[str]:
    """Every cell of a watchlist file, uppercased and stripped."""
    with open(path, newline="") as handle:
        return [
            token.strip().upper()
            for row in csv.reader(handle)
            for token in row
            if token.strip()
        ]


def watchlist_stamp(directory: Path | str) -> float:
    """The latest modification time among the ``*.csv`` files in ``directory``.

    Cached readers take this as an argument: editing a watchlist changes the
    stamp, which changes their cache key, so the next rerun re-reads the lists
    instead of serving the pre-edit universe until a TTL expires.
    """
    directory = Path(directory)
    return max(
        (path.stat().st_mtime for path in directory.glob("*.csv")), default=0.0
    )


def read_watchlists(directory: Path | str) -> Dict[str, Watchlist]:
    """Resolve every ``*.csv`` in ``directory`` to its symbol tuple.

    Tokens that name another watchlist (case-insensitively, without the
    extension) expand to that list's symbols, recursively. References that
    would loop are ignored rather than treated as symbols.
    """
    directory = Path(directory)
    raw: Dict[str, Sequence[str]] = {
        path.stem: _read_symbols(path) for path in sorted(directory.glob("*.csv"))
    }
    by_name: Mapping[str, str] = {name.lower(): name for name in raw}

    def resolve(name: str, visited: Tuple[str, ...]) -> Watchlist:
        symbols: List[str] = []
        for token in raw[name]:
            target = by_name.get(token.lower())
            if target is None:
                symbols.append(token)
            elif target not in visited:
                symbols.extend(resolve(target, visited + (target,)))
        return tuple(dict.fromkeys(symbols))

    return {name: resolve(name, (name,)) for name in raw}
