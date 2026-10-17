"""Tests for the Due Diligence page.

The page is snapshot-only: it must render every section offline from a hand-built
snapshot, and it must degrade to an empty state (never a live fetch) when no
snapshot is configured.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "surprises.py"
HARNESS = Path(__file__).resolve().parent / "_surprises_render_app.py"


def _load_page():
    spec = importlib.util.spec_from_file_location("surprises_module", PAGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section_control(app):
    return next(control for control in app.segmented_control if control.key == "harness_section")


def test_renderer_registry_covers_every_screen():
    page = _load_page()
    assert set(page.RENDERERS) == set(page.SECTION_TITLES)
    assert all(callable(renderer) for renderer in page.RENDERERS.values())


def test_every_section_renders_from_a_snapshot():
    app = AppTest.from_file(str(HARNESS), default_timeout=60)
    app.run()
    assert not app.exception, app.exception

    control = _section_control(app)
    for title in list(control.options):
        control.set_value(title)
        app.run()
        assert not app.exception, f"{title}: {app.exception}"


def test_screens_produce_results():
    app = AppTest.from_file(str(HARNESS), default_timeout=60)
    app.run()

    # Options pricing mismatch: the fixture holds two mispriced NIFTY strikes.
    assert len(app.dataframe) >= 1

    control = _section_control(app)
    control.set_value("Unusual volume in stocks")
    app.run()
    assert len(app.dataframe) >= 1, "the volume spike should produce a row"

    control = _section_control(app)
    control.set_value("Unusual moves in pairs")
    app.run()
    assert len(app.dataframe) >= 1, "the stretched AAA/BBB pair should be flagged"


def test_page_renders_without_a_snapshot(tmp_path, monkeypatch):
    """With no snapshot the page shows empty states, not a live fetch."""
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "empty"))

    app = AppTest.from_file(str(PAGE), default_timeout=60)
    app.run()
    assert not app.exception, app.exception

    header = " ".join(element.value for element in app.html)
    assert "Due Diligence" in header

    control = next(control for control in app.segmented_control if control.key == "dd-section")
    assert tuple(control.options) == _load_page().SECTION_TITLES

    for title in list(control.options):
        control.set_value(title)
        app.run()
        assert not app.exception, f"{title}: {app.exception}"
