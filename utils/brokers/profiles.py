"""Saved column mappings for brokers we do not ship a built-in profile for.

A file is mapped once in the import page's editor, saved under ``profiles/``
(git-ignored, alongside ``portfolios/``), and reused from then on. The saved
shape is deliberately plain JSON — a name and a ``target → source column`` map —
so a mapping can be reviewed, edited, or committed as a built-in profile later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Mapping, Optional

from utils.brokers.base import BrokerProfile

PROFILE_DIR = (Path(__file__).resolve().parent.parent.parent / "profiles").resolve()


def _slug(name: str) -> str:
    """A filesystem-safe stem for a profile name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name).strip()).strip("-._")
    return cleaned.lower()[:60]


def _path(name: str) -> Optional[Path]:
    slug = _slug(name)
    if not slug:
        return None
    path = (PROFILE_DIR / f"{slug}.json").resolve()
    return path if PROFILE_DIR in path.parents else None


def saved_profiles() -> Dict[str, Mapping[str, str]]:
    """Every saved mapping, keyed by its display name."""
    profiles: Dict[str, Mapping[str, str]] = {}
    if not PROFILE_DIR.is_dir():
        return profiles
    for path in sorted(PROFILE_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        columns = payload.get("columns")
        if isinstance(columns, Mapping) and columns:
            profiles[str(payload.get("name") or path.stem)] = dict(columns)
    return profiles


def save_profile(name: str, columns: Mapping[str, str]) -> Optional[Path]:
    """Persist a ``target → source column`` mapping under ``profiles/``."""
    path = _path(name)
    if path is None or not columns:
        return None
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, "columns": dict(columns)}, indent=2))
    return path


def profile_from_mapping(name: str, columns: Mapping[str, str]) -> BrokerProfile:
    """A :class:`BrokerProfile` from a saved mapping.

    ``columns`` maps a target column to the *source* header it came from, which
    is exactly the alias tuple the reader looks for — one alias per target.
    """
    return BrokerProfile(
        name=name,
        signature=(),
        columns={target: (source,) for target, source in columns.items() if source},
    )
