"""The project is emoji-free by rule (see AGENTS.md).

Iconography is Material Symbols plus the committed SVGs in ``assets/``; every
emoji is a regression. This guard walks the tracked text files and fails on the
first one it finds, so the rule cannot rot silently.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Directories that are generated, vendored or otherwise not ours to police.
SKIP_DIRS = {".git", ".venv", ".pytest_cache", "__pycache__", "snapshots"}

# Text formats we author by hand. Data files (CSV/XLSX) and images are skipped.
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".yml", ".yaml", ".css", ".svg", ".txt"}

# Pictographs, misc symbols/dingbats, and the variation selector that turns a
# glyph into its emoji presentation. Deliberately excludes typographic marks the
# project does use (— en/em dashes, · middot, ₹ rupee, arrows, °C).
EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs: faces, transport, food, flags
    "\U00002600-\U000027BF"  # misc symbols and dingbats (check marks, warnings)
    "\U00002B00-\U00002BFF"  # arrows and stars
    "\u2705\u274C\u26A0\u2139\u2699\u23F3\uFE0F"
    "]"
)


def _text_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        yield path


def test_no_emoji_in_repository():
    offenders = []
    for path in _text_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EMOJI.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

    if offenders:
        pytest.fail(
            "Emoji are not allowed (see AGENTS.md); use Material Symbols or the "
            "SVGs in assets/ instead:\n  " + "\n  ".join(offenders)
        )


def test_stylesheet_survives_the_sanitizer():
    """The theme stylesheet must stay free of angle brackets.

    ``utils.theme.apply_theme`` passes a style-only payload to ``st.html``.
    Streamlit drops such an element entirely when its text contains a tag-like
    ``<name>`` sequence, and because the stylesheet is one element that silently
    removes the entire theme — the app renders unstyled with no error at all.
    """
    from utils import theme

    stylesheet = theme._stylesheet()
    assert "<" not in stylesheet, (
        "the theme stylesheet contains '<', which makes Streamlit drop the whole "
        "style-only st.html payload (see utils/theme.py)"
    )
