"""The cached snapshot store the pages read through.

:mod:`utils.snapshot` deliberately never imports Streamlit, so the nightly job
can use it; this is the one Streamlit-facing piece. The store is built once per
process from the ``[snapshot]`` secrets table (or the ``SNAPSHOT_*`` env vars),
and degrades to a local directory when nothing is configured — in which case the
loaders simply fall back to live fetches.
"""

from __future__ import annotations

import streamlit as st

from utils import snapshot


@st.cache_resource(show_spinner=False)
def snapshot_store():
    """The configured snapshot store, shared by every page."""
    try:
        secrets = st.secrets.to_dict()
    except Exception:  # no secrets file, or running outside Streamlit
        secrets = {}
    return snapshot.SnapshotConfig.from_secrets(secrets).store()
