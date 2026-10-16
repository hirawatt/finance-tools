# AGENTS.md

Guidance for coding agents working in this repository.

## Hard rules

- **Never push commits.** Commit locally only; leave pushing to the maintainer.

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

## Conventions

- Keep analytics logic in `utils/` as pure functions over pandas objects so it
  stays testable; keep Streamlit and network concerns in `pages/`.
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
- Check off the matching README roadmap item when completing one.
