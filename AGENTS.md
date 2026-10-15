# AGENTS.md

Guidance for coding agents working in this repository.

## Hard rules

- **Never push commits.** Commit locally only; leave pushing to the maintainer.

## Project

A Streamlit app ("The Trading Dashboard by Hirawat") for Indian capital-markets
analysis. Entry point is `main.py`; the individual tools live in `pages/`;
shared helpers live in `utils/`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

## Running

```bash
.venv/bin/streamlit run main.py
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
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
- Dependencies are pinned in `requirements.txt`; test-only deps in
  `requirements-dev.txt`.
- Check off the matching README roadmap item when completing one.
