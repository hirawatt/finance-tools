# AGENTS.md

Guidance for coding agents working in this repository.

## Hard rules

- **Never push commits.** Commit locally only; leave pushing to the maintainer.
- **No emoji, anywhere.** Not in the UI, page titles, widget labels, docs or
  commits. Use the Material Symbols font Streamlit already bundles for
  iconography — `:material/<name>:` for `st.Page`/widget `icon=` arguments, and
  `utils.theme.glyph("<name>")` inside custom HTML — with committed SVG brand
  marks in `assets/` (`favicon.svg`, `logo.svg`) for the favicon and the sidebar
  lockup. `tests/test_style.py` fails the build if an emoji creeps back in.

## Project

A Streamlit app ("The Trading Dashboard by Hirawat") for Indian capital-markets
analysis. Entry point is `main.py`; the individual tools live in `pages/`;
shared helpers live in `utils/`.

## Setup

`uv` manages the interpreter (pinned in `.python-version`) and the virtualenv.

```bash
uv sync            # creates .venv from uv.lock, dev deps included
```

Install uv itself first if needed: `brew install uv`, or see
<https://docs.astral.sh/uv/getting-started/installation/>.

## Running

```bash
uv run streamlit run main.py
docker build -t finance-tools .   # the image published to GHCR
```

## Tests

```bash
uv run pytest -q
```

- Tests must not touch the network. Pure analytics helpers are unit-tested
  directly; functions that fetch (yfinance) are wrapped in `@st.cache_data` in
  the page and only their pure parts are tested.
- A test module that stubs `sys.modules` (pandas/streamlit/plotly) must restore
  the originals after importing the module under test — otherwise it poisons
  every other test module running in the same process.
- `streamlit.testing.v1.AppTest` resolves relative paths against the file that
  calls `from_file`, so pass an absolute path.
- CI runs this suite plus a check that `requirements.txt` matches `uv.lock`
  (`.github/workflows/ci.yml`), so regenerate it in the same commit as any
  dependency change.

## Conventions

- Keep analytics logic in `utils/` as pure functions over pandas objects so it
  stays testable; keep Streamlit and network concerns in `pages/`.
- Build every chart with `utils/charts.py` and render it through
  `theme.chart(fig, alt=...)` so the palette, axes and hover grammar stay
  consistent — never call `st.plotly_chart` directly or rely on Streamlit's
  chart theme, which would override the shared styling. Chart builders are pure
  (pandas in, a plotly figure out) and unit-tested without Streamlit.
- Register pages in `main.py` with `st.navigation` / `st.Page` (titles, icons
  and order live there); page modules use plain `snake_case` filenames and must
  not call `st.set_page_config`, which the entrypoint owns.
- Presentation lives in `.streamlit/config.toml` (colours, fonts, radii, chart
  palettes) plus `utils/theme.py` (the stylesheet Streamlit cannot express, and
  helpers such as `page_header`). Change the look there, not with per-page CSS,
  and import `utils.theme` only where the tests do not stub `sys.modules`.
- Analytics sections on the Co-Pilot are one renderer per section over a shared
  `AnalyticsContext`, registered in `SECTIONS`; add a section by writing a
  renderer and adding it to that mapping, and the tests pick it up.
- Cache network/Streamlit calls with `@st.cache_data`.
- Dependencies are declared in `pyproject.toml` and locked in `uv.lock`; change
  them with `uv add` / `uv remove` (or by editing `pyproject.toml` plus
  `uv lock`) and commit both files. Test-only deps go in the `dev` dependency
  group.
- `requirements.txt` is generated for Streamlit Community Cloud, which cannot
  read `uv.lock` — never edit it by hand; regenerate with
  `uv export --no-dev --no-emit-project --no-hashes --output-file requirements.txt`.
- The uv-managed `.venv` has no `pip`; run things through `uv run` and install
  through `uv sync` / `uv add`.
- Anything the app reads at runtime (data files, `DATA.md`, `indices/`) must
  stay out of `.dockerignore` and be committed: the published image is built
  from `Dockerfile` by `.github/workflows/docker.yml`.
- Check off the matching README roadmap item when completing one.
