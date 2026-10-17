"""Every Co-Pilot analytics section renders, offline.

The real page fetches prices, fundamentals, statements, surveillance lists and
the earnings calendar from Yahoo/NSE. ``_copilot_render_app.py`` swaps those
loaders for hand-built frames and renders whichever section is selected, so this
covers all seven renderers without the network and without a snapshot store.

The section list comes from the page itself, so adding a renderer there
automatically extends this test.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from pages import portfolio_analysis as co_pilot

HARNESS = Path(__file__).resolve().parent / "_copilot_render_app.py"


def test_every_analytics_section_renders():
    at = AppTest.from_file(str(HARNESS), default_timeout=60)
    at.run()
    assert not at.exception, f"Correlation raised: {at.exception}"

    # Guard the harness against the page's section list drifting away from it.
    assert tuple(at.segmented_control[0].options) == co_pilot.ANALYTICS_SECTIONS

    for section in co_pilot.ANALYTICS_SECTIONS:
        at.segmented_control[0].set_value(section)
        at.run()
        assert not at.exception, f"{section} raised: {at.exception}"


def test_sections_are_derived_from_their_renderers():
    """The labels and the renderers cannot drift apart."""
    assert co_pilot.ANALYTICS_SECTIONS == tuple(co_pilot.SECTIONS)
    assert all(callable(renderer) for renderer in co_pilot.SECTIONS.values())
