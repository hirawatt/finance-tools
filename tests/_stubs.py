"""Load app modules while ``pandas``/``streamlit`` are stubbed, without leaking.

Two test modules import a page with those packages replaced by mocks, because
the page touches them at import time. The app's *own* modules bind whatever they
see at import, so they have to be dropped afterwards or the next test module
inherits a mock — the trap AGENTS.md calls out.

Third-party modules are deliberately left in place: popping a C extension such
as numpy makes re-importing it later in the same process fail with "cannot load
module more than once per process".
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

_MISSING = object()


def _drop(name: str) -> None:
    """Remove ``name`` from ``sys.modules`` and from its parent package."""
    module = sys.modules.pop(name, None)
    parent_name, _, child = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    # ``from utils import x`` resolves the parent attribute before sys.modules,
    # so the attribute has to go too.
    if parent is not None and getattr(parent, child, None) is module:
        delattr(parent, child)


@contextmanager
def stubbed(*app_modules: str, **overrides):
    """Stub ``sys.modules`` for the block, then drop the app modules it created.

    ``app_modules`` names any further application modules imported inside the
    block that should be dropped afterwards; anything under ``utils`` is dropped
    automatically, and everything else (numpy, pandas' internals, ...) is left
    as it was.
    """
    before = set(sys.modules)
    saved = {name: sys.modules.get(name, _MISSING) for name in overrides}

    sys.modules.update(overrides)
    try:
        yield
    finally:
        for name in set(sys.modules) - before:
            if name == "utils" or name.startswith("utils.") or name in app_modules:
                _drop(name)
        for name, original in saved.items():
            if original is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
