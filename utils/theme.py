"""The dashboard's visual identity and reusable presentation helpers.

Streamlit's native theming (``.streamlit/config.toml``) owns the colours, fonts
and radii. This module fills the gaps it cannot reach — the hero banner on the
home page, carded metric/chart/table surfaces, sidebar polish — and exposes a
handful of small helpers so every page renders its headings, icons and charts
the same way. Chart *construction* lives in :mod:`utils.charts`; :func:`chart`
here is only the shared display wrapper. Iconography is Material Symbols (the
font Streamlit bundles); there are no emoji in the app, its pages or its docs.

Everything here is injected with :func:`st.html` rather than ``st.markdown``:
``st.html`` renders to its own element type, so a page's list of markdown
elements — which the tests assert against — stays exactly as the page wrote it.

The module holds no state and makes no network calls, so it is cheap to import
from the entrypoint or any page. (Pages whose tests stub ``sys.modules`` must
restore it afterwards — see the note in AGENTS.md — or the stub is what later
tests will import.)
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import streamlit as st

#: Repository root, so committed assets resolve no matter the working directory.
_ROOT = Path(__file__).resolve().parent.parent

#: The brand palette, and the single source of truth for every colour this
#: module styles. ``.streamlit/config.toml`` mirrors these values because it owns
#: the native theme; keeping the list here means the stylesheet and the handful
#: of colours pages reuse can never drift apart.
PALETTE = {
    "accent": "#1F6FEB",
    "accent_soft": "rgba(31, 111, 235, 0.10)",
    "ink": "#0B1220",
    "muted": "#64748B",
    "line": "#E2E8F0",
    "surface": "#FFFFFF",
    "radius": "0.75rem",
    "shadow-sm": "0 1px 2px rgba(15, 23, 42, 0.05)",
    "shadow-md": "0 10px 30px rgba(15, 23, 42, 0.09)",
}

#: The accent, for pages that hand-colour plotly traces Streamlit's chart theme
#: does not reach.
ACCENT = PALETTE["accent"]

#: Plotly config shared by every figure. The logo is dropped, and the select /
#: lasso tools (which do not fit a financial dashboard) go with it, leaving
#: zoom, pan, reset and the PNG export.
PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}

_CSS = """
/* ---- Frame -------------------------------------------------------- */
/* Drop Streamlit's rainbow top rule and let the page breathe. */
[data-testid="stDecoration"] { display: none; }
[data-testid="stHeader"] { background: transparent; }

[data-testid="stMainBlockContainer"] {
  max-width: 1280px;
  padding: 2.25rem 2.75rem 1.5rem;
}
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding: 1.4rem 1.1rem 1rem; }
}

/* ---- Sidebar ------------------------------------------------------ */
[data-testid="stSidebar"] { border-right: 1px solid var(--td-line); }
[data-testid="stSidebarContent"] { padding-top: 0.35rem; }
[data-testid="stSidebarNav"] { padding: 0.4rem 0.5rem 0.9rem; }
[data-testid="stSidebarNavLink"] {
  border-radius: 0.6rem;
  padding: 0.35rem 0.6rem;
  transition: background-color 0.15s ease;
}
[data-testid="stSidebarNavLink"]:hover { background-color: var(--td-accent-soft); }

/* ---- Icons -------------------------------------------------------- */
/* Material Symbols, the font Streamlit already bundles for navigation. No
   emoji: the same vocabulary as st.Page's :material/icon_name: icons. Keep
   angle brackets out of this stylesheet: Streamlit drops a style-only st.html
   payload whose text holds a tag-like angle-bracket sequence, which would
   silently strip the whole theme (see the guard in tests/test_style.py). */
.td-i {
  font-family: "Material Symbols Rounded";
  font-weight: normal;
  font-style: normal;
  font-size: 1.1em;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  word-wrap: normal;
  direction: ltr;
  font-feature-settings: "liga";
  -webkit-font-smoothing: antialiased;
  vertical-align: -0.18em;
}

/* ---- Typography --------------------------------------------------- */
h1, h2, h3, h4 { color: var(--td-ink); }
h1 { font-weight: 700 !important; letter-spacing: -0.025em; line-height: 1.15; }
h2 { font-weight: 700 !important; letter-spacing: -0.02em; }
h3 { font-weight: 600 !important; letter-spacing: -0.015em; }
p, li { line-height: 1.6; }
a { text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border-color: var(--td-line); margin: 1.15rem 0; }

/* ---- Metric cards ------------------------------------------------- */
/* Every st.metric becomes a KPI tile, like a broker's position summary. */
[data-testid="stMetric"] {
  background: var(--td-surface);
  border: 1px solid var(--td-line);
  border-radius: var(--td-radius);
  padding: 0.85rem 1rem 0.95rem;
  box-shadow: var(--td-shadow-sm);
  height: 100%;
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
  color: var(--td-muted) !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] > div { font-weight: 700; letter-spacing: -0.02em; }
[data-testid="stMetricDelta"] { font-weight: 600; }
[data-testid="stHorizontalBlock"] { align-items: stretch; }

/* ---- Tables, charts and code -------------------------------------- */
[data-testid="stDataFrame"] {
  border: 1px solid var(--td-line) !important;
  border-radius: var(--td-radius);
  box-shadow: var(--td-shadow-sm);
}
[data-testid="stPlotlyChart"], [data-testid="stArrowVegaLiteChart"] {
  background: var(--td-surface);
  border: 1px solid var(--td-line);
  border-radius: var(--td-radius);
  padding: 0.4rem 0.4rem 0;
  box-shadow: var(--td-shadow-sm);
}
[data-testid="stCode"], [data-testid="stCodeBlock"] {
  border-radius: var(--td-radius);
  border: 1px solid var(--td-line);
}

/* ---- Controls ----------------------------------------------------- */
.stButton > button, .stDownloadButton > button,
[data-testid="stBaseButton-secondary"] {
  border-radius: 0.6rem;
  font-weight: 600;
}
.stButton > button:hover, .stDownloadButton > button:hover,
[data-testid="stBaseButton-secondary"]:hover {
  border-color: var(--td-accent);
  color: var(--td-accent);
}
[data-testid="stBaseButton-primary"] {
  border-radius: 0.6rem;
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(31, 111, 235, 0.35);
}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  border-radius: 0.55rem;
}
[data-baseweb="tag"] { border-radius: 0.4rem; }
[data-testid="stAlert"] { border-radius: 0.65rem; }

/* ---- Tabs and expanders ------------------------------------------- */
.stTabs [data-baseweb="tab-list"] {
  gap: 0.35rem;
  border-bottom: 1px solid var(--td-line);
}
.stTabs [data-baseweb="tab"] {
  height: 2.75rem;
  padding: 0 0.9rem;
  border-radius: 0.6rem 0.6rem 0 0;
  font-weight: 600;
  color: var(--td-muted);
}
.stTabs [data-baseweb="tab"][aria-selected="true"] { color: var(--td-accent); }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--td-accent); }
.stTabs [data-baseweb="tab-border"] { background-color: transparent; }

[data-testid="stExpander"] {
  border: 1px solid var(--td-line);
  border-radius: var(--td-radius);
  background: var(--td-surface);
  box-shadow: var(--td-shadow-sm);
  overflow: hidden;
}
[data-testid="stExpander"] summary { font-weight: 600; }
[data-testid="stExpander"] summary:hover { color: var(--td-accent); }

/* ---- Hero banner (home page) -------------------------------------- */
.td-hero {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  align-items: center;
  gap: clamp(1.2rem, 3vw, 2.5rem);
  margin-bottom: 0.4rem;
  padding: clamp(1.6rem, 3.5vw, 3rem);
  border-radius: 1.1rem;
  color: #F8FAFC;
  background:
    radial-gradient(900px 420px at 100% 0%, rgba(31, 111, 235, 0.55), transparent 60%),
    radial-gradient(700px 380px at 0% 100%, rgba(18, 184, 134, 0.30), transparent 55%),
    linear-gradient(135deg, #0A1729 0%, #0E2A4D 55%, #0A1729 100%);
  box-shadow: var(--td-shadow-md);
}
/* A single column when there is no illustration. */
.td-hero:not(:has(.td-hero__art)) { grid-template-columns: 1fr; }
.td-hero::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.10) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.10) 1px, transparent 1px);
  background-size: 44px 44px;
  -webkit-mask-image: radial-gradient(700px 300px at 20% 0%, #000 0%, transparent 80%);
  mask-image: radial-gradient(700px 300px at 20% 0%, #000 0%, transparent 80%);
}
.td-hero__body { position: relative; min-width: 0; }
/* The brand lockup above the eyebrow: the app mark plus name and byline. */
.td-hero__brand {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin-bottom: 1.1rem;
}
.td-hero__mark {
  width: 2.6rem;
  height: 2.6rem;
  border-radius: 0.75rem;
  box-shadow: 0 6px 18px rgba(2, 8, 23, 0.45);
}
.td-hero__name {
  font-size: 1.02rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #FFFFFF;
}
.td-hero__byline {
  margin-top: 0.1rem;
  font-size: 0.64rem;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #8FB6F5;
}
.td-hero__art {
  position: relative;
  display: grid;
  place-items: center;
  min-width: 0;
}
.td-hero__art img {
  width: 100%;
  max-width: 31rem;
  height: auto;
  filter: drop-shadow(0 18px 40px rgba(2, 8, 23, 0.45));
}
/* Stack the hero on narrow screens, and let the illustration go: it is
   decorative and costs a lot of vertical space on a phone. Declared after the
   base rules above so it is not overridden by their ``display``. */
@media (max-width: 880px) {
  .td-hero { grid-template-columns: 1fr; }
  .td-hero__art { display: none; }
}
/* Let a row of KPI tiles wrap instead of squeezing their labels. */
@media (max-width: 1000px) {
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) {
    flex-wrap: wrap;
  }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"])
    > [data-testid="stColumn"] {
    flex: 1 1 44%;
    min-width: 9rem;
  }
}
.td-hero__eyebrow {
  position: relative;
  margin-bottom: 0.7rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #8FB6F5;
}
.td-hero__title {
  position: relative;
  margin: 0;
  font-size: clamp(1.9rem, 1.2rem + 2.4vw, 3rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.08;
  color: #FFFFFF;
}
.td-hero__subtitle {
  position: relative;
  margin: 0.9rem 0 0;
  max-width: 62ch;
  font-size: clamp(0.95rem, 0.9rem + 0.3vw, 1.1rem);
  line-height: 1.6;
  color: #CBD5E1;
}
.td-hero__chips { position: relative; display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1.4rem; }
.td-hero__chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.8rem;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 0.78rem;
  font-weight: 600;
  color: #E2E8F0;
}
.td-hero__chip .td-i { color: #8FB6F5; }

/* ---- Page and section headings ------------------------------------ */
.td-ph { margin: 0 0 1.4rem; }
.td-ph__title {
  margin: 0;
  font-size: clamp(1.6rem, 1.3rem + 1vw, 2.05rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: var(--td-ink);
}
.td-ph__sub { margin: 0.45rem 0 0; max-width: 92ch; color: var(--td-muted); font-size: 0.96rem; }
.td-ph__rule {
  width: 3rem;
  height: 3px;
  margin-top: 0.85rem;
  border-radius: 999px;
  background: var(--td-accent);
}

.td-sec { margin: 1.6rem 0 0.5rem; }
.td-sec__title { margin: 0; font-size: 1.15rem; font-weight: 700; letter-spacing: -0.015em; color: var(--td-ink); }
.td-sec__cap { margin: 0.3rem 0 0; color: var(--td-muted); font-size: 0.88rem; }

/* ---- Feature cards ------------------------------------------------- */
.td-card { display: flex; flex-direction: column; gap: 0.5rem; }
.td-card__icon {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.75rem;
  background: var(--td-accent-soft);
  color: var(--td-accent);
  font-size: 1.35rem;
}
.td-card__title { font-size: 1.02rem; font-weight: 700; letter-spacing: -0.01em; color: var(--td-ink); }
.td-card__body { margin: 0; color: var(--td-muted); font-size: 0.9rem; line-height: 1.55; }

/* Bordered containers opened with a ``td-card`` key lift on hover. */
[class*="st-key-td-card"] { transition: transform 0.16s ease; }
[class*="st-key-td-card"]:hover { transform: translateY(-2px); }
[class*="st-key-td-card"]:hover [data-testid="stVerticalBlock"] {
  border-color: rgba(31, 111, 235, 0.5);
}

/* ---- Workflow steps ----------------------------------------------- */
/* The home page's "what you can do here" strip: a numbered run of cards. */
.td-steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12.5rem, 1fr));
  gap: 1rem;
}
.td-step {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  padding: 1.15rem 1.2rem 1.2rem;
  border: 1px solid var(--td-line);
  border-radius: var(--td-radius);
  background: var(--td-surface);
  box-shadow: var(--td-shadow-sm);
  transition: transform 0.16s ease, border-color 0.16s ease;
}
.td-step:hover { transform: translateY(-2px); border-color: rgba(31, 111, 235, 0.5); }
.td-step__top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.td-step__icon {
  display: grid;
  place-items: center;
  width: 2.4rem;
  height: 2.4rem;
  border-radius: 0.7rem;
  background: var(--td-accent-soft);
  color: var(--td-accent);
  font-size: 1.3rem;
}
.td-step__num {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--td-muted);
}
.td-step__title { font-size: 1rem; font-weight: 700; letter-spacing: -0.01em; color: var(--td-ink); }
.td-step__body { margin: 0; color: var(--td-muted); font-size: 0.89rem; line-height: 1.55; }

/* ---- Tool directory ----------------------------------------------- */
/* A responsive logo wall: as many cards per row as the width allows. */
.td-tools {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: 1rem;
}
/* Each card is one outbound link, so the whole tile is the target. */
.td-tool {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  padding: 1.1rem 1.15rem 1rem;
  border: 1px solid var(--td-line);
  border-radius: var(--td-radius);
  background: var(--td-surface);
  box-shadow: var(--td-shadow-sm);
  color: inherit;
  text-decoration: none;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}
.td-tool:hover {
  transform: translateY(-2px);
  border-color: rgba(31, 111, 235, 0.5);
  box-shadow: var(--td-shadow-md);
  text-decoration: none;
}
.td-tool__mark { display: grid; place-items: center; height: 3.25rem; }
.td-tool__logo { max-height: 3.25rem; max-width: 100%; object-fit: contain; }
.td-tool__mono {
  display: grid;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border-radius: 0.85rem;
  background: var(--td-accent-soft);
  color: var(--td-accent);
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.td-tool__name { font-size: 1.02rem; font-weight: 700; color: var(--td-ink); }
.td-tool__domain {
  margin-top: 0.1rem;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 0.74rem;
  color: var(--td-muted);
  word-break: break-all;
}
.td-tool__desc { margin: 0; flex: 1; color: var(--td-muted); font-size: 0.88rem; line-height: 1.5; }
.td-tool__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding-top: 0.15rem;
}
.td-tool__tag {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  background: var(--td-accent-soft);
  color: var(--td-accent);
  font-size: 0.72rem;
  font-weight: 600;
}
.td-tool__open {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--td-accent);
  font-size: 0.8rem;
  font-weight: 600;
}
.td-tool__open .td-i { font-size: 1rem; }

/* ---- Footer -------------------------------------------------------- */
.td-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.6rem 1.5rem;
  margin-top: 2.6rem;
  padding-top: 1rem;
  border-top: 1px solid var(--td-line);
  color: var(--td-muted);
  font-size: 0.82rem;
}
.td-footer a { color: var(--td-muted); font-weight: 600; }
.td-footer a:hover { color: var(--td-accent); }
"""


def _stylesheet() -> str:
    """The generated theme variables, followed by the static rules.

    Rendering ``:root`` from :data:`PALETTE` keeps the colour list to one place;
    :data:`_CSS` holds only the rules that reference those variables.
    """
    variables = "\n".join(
        f"  --td-{name.replace('_', '-')}: {value};" for name, value in PALETTE.items()
    )
    return f":root {{\n{variables}\n}}\n{_CSS}"


def apply_theme() -> None:
    """Inject the global stylesheet.

    Called once from the entrypoint. ``st.html`` sends a style-only payload to
    the event container, so it takes no space in the page layout.
    """
    st.html(f"<style>{_stylesheet()}</style>")


def glyph(name: str) -> str:
    """Inline markup for a Material Symbols icon, for use inside custom HTML.

    ``name`` is a Material Symbols name — the same vocabulary as
    ``st.Page(icon=":material/<name>:")`` — so a typo raises instead of quietly
    rendering the literal text. There are no emoji anywhere in the app: this and
    ``st.Page``'s icons are the only iconography.
    """
    # Imported here rather than at module scope so this module stays importable
    # when a test stubs ``streamlit`` with a bare mock (AGENTS.md).
    from streamlit.string_util import is_material_icon

    if not is_material_icon(name):
        raise ValueError(
            f"{name!r} is not a Material Symbols icon name; "
            "see https://fonts.google.com/icons?icon.set=Material+Symbols"
        )
    return f'<span class="td-i" aria-hidden="true">{name}</span>'


def hero(
    eyebrow: str,
    title: str,
    subtitle: str,
    chips: tuple[tuple[str, str], ...] = (),
    *,
    graphic: Optional[str] = None,
    mark: Optional[str] = None,
    name: Optional[str] = None,
    byline: Optional[str] = None,
) -> None:
    """Render the dark hero banner at the top of a page.

    ``chips`` are ``(icon_name, label)`` pairs rendered as pill badges.
    ``graphic`` is an optional image (a path relative to the repository root,
    inlined as a data URI) shown in the right-hand column — it is decorative, so
    it carries an empty ``alt``. ``mark``, ``name`` and ``byline`` render an
    optional brand lockup above the eyebrow, and all three are omitted when
    ``mark`` is not a committed file.
    """
    chip_html = "".join(
        f'<span class="td-hero__chip">{glyph(g)}{label}</span>' for g, label in chips
    )

    brand = ""
    mark_uri = _logo_data_uri(mark) if mark else None
    if mark_uri:
        name_html = f'<div class="td-hero__name">{escape(name)}</div>' if name else ""
        byline_html = f'<div class="td-hero__byline">{escape(byline)}</div>' if byline else ""
        brand = (
            '<div class="td-hero__brand">'
            f'<img class="td-hero__mark" src="{mark_uri}" alt="">'
            f"<div>{name_html}{byline_html}</div>"
            "</div>"
        )

    art = ""
    graphic_uri = _logo_data_uri(graphic) if graphic else None
    if graphic_uri:
        art = f'<div class="td-hero__art"><img src="{graphic_uri}" alt=""></div>'

    st.html(
        '<section class="td-hero">'
        '<div class="td-hero__body">'
        + brand
        + f'<div class="td-hero__eyebrow">{escape(eyebrow)}</div>'
        f'<h1 class="td-hero__title">{escape(title)}</h1>'
        f'<p class="td-hero__subtitle">{escape(subtitle)}</p>'
        + (f'<div class="td-hero__chips">{chip_html}</div>' if chip_html else "")
        + "</div>"
        + art
        + "</section>"
    )


def steps(items: Iterable[tuple[str, str, str]]) -> None:
    """Render the numbered workflow strip: ``(icon_name, title, body)`` triples.

    A responsive grid of cards, each with a Material Symbols badge and its place
    in the sequence, used on the home page to explain the app at a glance.
    """
    cards = "".join(
        '<div class="td-step">'
        '<div class="td-step__top">'
        f'<div class="td-step__icon">{glyph(icon)}</div>'
        f'<div class="td-step__num">{index:02d}</div>'
        "</div>"
        f'<div class="td-step__title">{escape(title)}</div>'
        f'<p class="td-step__body">{escape(body)}</p>'
        "</div>"
        for index, (icon, title, body) in enumerate(items, start=1)
    )
    st.html(f'<div class="td-steps">{cards}</div>')


def page_header(title: str, subtitle: str | None = None) -> None:
    """Render a page title with a subtitle and a small accent rule."""
    sub_html = f'<p class="td-ph__sub">{subtitle}</p>' if subtitle else ""
    st.html(
        '<header class="td-ph">'
        f'<h1 class="td-ph__title">{title}</h1>{sub_html}'
        '<div class="td-ph__rule"></div>'
        "</header>"
    )


def section_header(title: str, caption: str | None = None) -> None:
    """Render a section heading with an optional caption underneath."""
    cap_html = f'<p class="td-sec__cap">{caption}</p>' if caption else ""
    st.html(f'<div class="td-sec"><h3 class="td-sec__title">{title}</h3>{cap_html}</div>')


def chart(fig, *, alt: str | None = None, key: str | None = None) -> None:
    """Render a Plotly figure with the dashboard's shared display config.

    ``theme="streamlit"`` is deliberately *not* used: the figures are styled by
    :mod:`utils.charts`, and letting Streamlit re-theme them would override the
    palette, fonts and axis treatment the module sets. ``alt`` describes the
    chart for screen readers and is required on every call.
    """
    st.plotly_chart(
        fig, width="stretch", alt=alt, config=PLOTLY_CONFIG, theme=None, key=key
    )


def metric_row(items: Iterable[Sequence], columns: Optional[int] = None) -> None:
    """Render one row of KPI cards.

    Each item is ``(label, value)`` or ``(label, value, delta)``; an optional
    fourth element is a mapping of extra keyword arguments passed through to
    :func:`st.metric` — ``chart_data`` for a sparkline, ``delta_description``,
    ``help``, and so on. ``columns`` defaults to one column per item, so
    callers never repeat the ``st.columns``/``st.metric`` pair by hand.
    """
    items = list(items)
    if not items:
        return

    for column, item in zip(st.columns(columns or len(items)), items):
        label, value, *rest = item
        delta = rest[0] if rest else None
        options = rest[1] if len(rest) > 1 else {}
        column.metric(label, value, delta=delta, **options)


def printf_format(pattern: str) -> str:
    """Translate a ``str.format`` number pattern into printf for ``column_config``.

    ``"₹{:,.0f}"`` becomes ``"₹%,.0f"`` and ``"{:.1f}%"`` becomes ``"%.1f%%"``,
    so call sites keep writing Python format strings while the cells are
    formatted by :func:`st.column_config.NumberColumn` — the Streamlit-native
    way; a pandas Styler is reserved for colouring only.
    """
    prefix, _, rest = pattern.partition("{")
    spec, _, suffix = rest.partition("}")
    # Drop the format spec's leading ":" ("{:,.0f}" -> ",.0f").
    return f"{prefix}%{spec.removeprefix(':')}" + suffix.replace("%", "%%")


def card(
    icon: str,
    title: str,
    body: str,
    *,
    key: Optional[str] = None,
    action: Optional[Callable[[], None]] = None,
) -> None:
    """Render a bordered card: an icon badge, a title and supporting copy.

    ``key`` gives the container a stable identity (its ``st-key-<key>`` class is
    what the hover styling targets); ``action`` renders an optional footer, such
    as the page link :func:`feature_card` adds.
    """
    with st.container(border=True, key=key):
        st.markdown(
            '<div class="td-card">'
            f'<div class="td-card__icon">{glyph(icon)}</div>'
            f'<div class="td-card__title">{title}</div>'
            f'<p class="td-card__body">{body}</p>'
            "</div>",
            unsafe_allow_html=True,
        )
        if action is not None:
            action()


def feature_card(
    *,
    key: str,
    icon: str,
    title: str,
    body: str,
    page: str,
    label: str = "Open",
) -> None:
    """A :func:`card` that links through to ``page``.

    ``icon`` is a Material Symbols name, rendered by :func:`glyph`.
    """
    card(
        icon,
        title,
        body,
        key=key,
        action=lambda: st.page_link(page, label=label, width="stretch"),
    )


def _logo_data_uri(relative_path: str) -> Optional[str]:
    """Inline a committed logo as a data URI, or ``None`` when it is absent.

    Data URIs keep the card markup self-contained: nothing depends on Streamlit
    serving a static directory, and the committed files stay the source of truth.
    """
    path = _ROOT / relative_path
    if not path.is_file():
        return None
    mime = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _tool_mark(item: Mapping) -> str:
    """The logo tile for one directory entry, falling back to its initials."""
    logo = item.get("logo")
    uri = _logo_data_uri(logo) if logo else None
    if uri:
        return (
            '<div class="td-tool__mark">'
            f'<img class="td-tool__logo" src="{uri}" alt="{escape(item["name"])} logo">'
            "</div>"
        )
    initials = item.get("initials") or "".join(word[0] for word in item["name"].split())[:2]
    return (
        '<div class="td-tool__mark">'
        f'<span class="td-tool__mono" aria-hidden="true">{escape(initials.upper())}</span>'
        "</div>"
    )


def _tool_card(item: Mapping) -> str:
    """Markup for one external-tool card: the whole tile links out to ``url``."""
    domain = urlparse(item["url"]).netloc
    if domain.startswith("www."):
        domain = domain[4:]
    tag = item.get("tag")
    tag_html = f'<span class="td-tool__tag">{escape(tag)}</span>' if tag else ""
    return (
        f'<a class="td-tool" href="{escape(item["url"], quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
        + _tool_mark(item)
        + '<div class="td-tool__head">'
        + f'<div class="td-tool__name">{escape(item["name"])}</div>'
        + f'<div class="td-tool__domain">{escape(domain)}</div>'
        + "</div>"
        + f'<p class="td-tool__desc">{escape(item["description"])}</p>'
        + '<div class="td-tool__meta">'
        + tag_html
        + f'<span class="td-tool__open">{glyph("open_in_new")}<span>Visit</span></span>'
        + "</div>"
        + "</a>"
    )


def tool_grid(items: Iterable[Mapping]) -> None:
    """Render a responsive grid of external-tool cards.

    Each item is a mapping of ``name``, ``url`` and ``description``, plus an
    optional ``tag`` and an optional ``logo`` (a path relative to the repository
    root). Entries without a usable ``logo`` fall back to an ``initials`` tile,
    which is derived from the name when not given, so the grid never renders a
    broken image. The entire card is an outbound link opened in a new tab.
    """
    cards = "".join(_tool_card(item) for item in items)
    st.html(f'<div class="td-tools">{cards}</div>')


def footer() -> None:
    """Render the shared, slim footer shown at the bottom of every page."""
    st.html(
        '<footer class="td-footer">'
        "<span>The Trading Dashboard by Hirawat — Indian capital-markets analytics.</span>"
        '<span><a href="https://github.com/hirawatt/finance-tools" target="_blank">'
        "Source</a> · <a href=\"https://github.com/hirawatt/finance-tools/issues\" "
        'target="_blank">Report a bug</a></span>'
        "</footer>"
    )
