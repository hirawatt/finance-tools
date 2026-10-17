"""The Tool Directory: a grid of outbound links, rendered without any network.

AppTest resolves relative paths against the file that calls it, so the page path
is absolute (see AGENTS.md). The card markup is injected with ``st.html``, so the
assertions read the HTML payload rather than the page's markdown.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import pages.tool_directory as tool_directory

ROOT = Path(__file__).resolve().parent.parent
PAGE_PATH = ROOT / "pages" / "tool_directory.py"


def test_tool_directory_renders_a_card_per_tool():
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"App raised an exception during run: {at.exception}"

    html = " ".join(element.value for element in at.html)
    # ``class="td-tool"`` is the anchor only; the inner spans use longer names.
    assert html.count('class="td-tool"') == len(tool_directory.TOOLS)
    for tool in tool_directory.TOOLS:
        assert tool["url"] in html
        assert tool["name"] in html


def test_tools_are_unique_and_https():
    urls = [tool["url"] for tool in tool_directory.TOOLS]
    assert len(urls) == len(set(urls)), "duplicate tool URLs"
    assert all(url.startswith("https://") for url in urls)


def test_every_declared_logo_is_committed():
    for tool in tool_directory.TOOLS:
        logo = tool.get("logo")
        if logo:
            path = ROOT / logo
            assert path.is_file(), f"missing logo for {tool['name']}: {logo}"
            assert path.stat().st_size > 0
