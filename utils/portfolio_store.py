"""Where a portfolio lives.

Two backends, by design:

* :class:`SessionStore` — the default. The active portfolio lives in
  ``st.session_state`` and never touches disk, which is what "privacy focused"
  means for a public app: uploading a file reveals nothing after the tab closes.
* :class:`LocalStore` — opt-in. One canonical CSV per client under ``portfolios/``
  (git-ignored), for the person who wants yesterday's book back tomorrow.

Both implement :class:`PortfolioStore`, so the intended PocketBase backend (with
auth) drops in behind the same three methods without the pages changing. Nothing
here imports Streamlit at module load, so the file backend is unit-testable on
its own.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_DIR = (_ROOT / "portfolios").resolve()

#: Keys the active portfolio is held under in ``st.session_state``.
ACTIVE_FRAME_KEY = "active_portfolio"
ACTIVE_LABEL_KEY = "active_portfolio_label"


@runtime_checkable
class PortfolioStore(Protocol):
    """The seam every storage backend implements."""

    def list(self) -> List[str]:
        """Client names with a stored portfolio."""

    def load(self, client: str) -> Optional[pd.DataFrame]:
        """The canonical frame for ``client``, or ``None``."""

    def save(self, client: str, frame: pd.DataFrame) -> None:
        """Persist ``frame`` as ``client``'s portfolio."""

    def delete(self, client: str) -> None:
        """Forget ``client``'s portfolio."""


def _slug(client: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(client).strip()).strip("-._")
    return cleaned[:80]


def client_path(client: str, root: Optional[Path] = None) -> Optional[Path]:
    """A traversal-safe CSV path for ``client`` — ``None`` if the name is empty.

    The resolved path must sit directly under ``root``, the same guarantee
    ``utils.custom_indices.get_safe_path`` gives watchlists.
    """
    slug = _slug(client)
    if not slug:
        return None
    base = (root or PORTFOLIO_DIR).resolve()
    path = (base / f"{slug}.csv").resolve()
    return path if base in path.parents else None


class LocalStore:
    """Canonical holdings as one CSV per client under a local directory."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or PORTFOLIO_DIR).resolve()

    def list(self) -> List[str]:
        if not self.root.is_dir():
            return []
        return sorted(path.stem for path in self.root.glob("*.csv"))

    def load(self, client: str) -> Optional[pd.DataFrame]:
        path = client_path(client, self.root)
        if path is None or not path.is_file():
            return None
        try:
            return pd.read_csv(path)
        except (OSError, ValueError):
            return None

    def save(self, client: str, frame: pd.DataFrame) -> None:
        path = client_path(client, self.root)
        if path is None:
            raise ValueError("A client name is required to save a portfolio.")
        self.root.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)

    def delete(self, client: str) -> None:
        path = client_path(client, self.root)
        if path is not None and path.is_file():
            path.unlink()


# Backwards-friendly module functions over the default local store.
def list_saved() -> List[str]:
    return LocalStore().list()


def load_saved(client: str) -> Optional[pd.DataFrame]:
    return LocalStore().load(client)


def save_local(client: str, frame: pd.DataFrame) -> Optional[Path]:
    LocalStore().save(client, frame)
    return client_path(client)


def delete_saved(client: str) -> None:
    LocalStore().delete(client)


# --------------------------------------------------------------------------- #
# The active portfolio (session-scoped, nothing on disk)
# --------------------------------------------------------------------------- #
def set_active(frame: pd.DataFrame, *, label: str = "") -> None:
    """Make ``frame`` the portfolio the Co-Pilot analyses, for this session only."""
    import streamlit as st

    st.session_state[ACTIVE_FRAME_KEY] = frame
    st.session_state[ACTIVE_LABEL_KEY] = label


def get_active() -> Optional[pd.DataFrame]:
    """The session's active portfolio, or ``None`` when it is using sample data."""
    import streamlit as st

    frame = st.session_state.get(ACTIVE_FRAME_KEY)
    return frame if isinstance(frame, pd.DataFrame) else None


def active_label() -> str:
    import streamlit as st

    return st.session_state.get(ACTIVE_LABEL_KEY, "")


def clear_active() -> None:
    import streamlit as st

    st.session_state.pop(ACTIVE_FRAME_KEY, None)
    st.session_state.pop(ACTIVE_LABEL_KEY, None)
