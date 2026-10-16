# syntax=docker/dockerfile:1

# Both stages must run the same interpreter: the virtualenv built in `builder`
# is copied into `runtime`. Declared once here so they cannot drift.
ARG PYTHON_IMAGE=python:3.15-slim

# The uv binary is copied out of its own image rather than pip-installed, so the
# build does not need a working Python on PATH just to install the installer.
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv


# --------------------------------------------------------------------------- #
# Dependencies: resolved from pyproject.toml + uv.lock, never from a re-resolve
# --------------------------------------------------------------------------- #
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies before source: this layer only rebuilds when the lock changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


# --------------------------------------------------------------------------- #
# Runtime: the venv plus the app, no uv, no build cache, no compiler
# --------------------------------------------------------------------------- #
FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # Sensible container defaults; all of these are plain Streamlit options and
    # can be overridden with -e or a mounted .streamlit/config.toml.
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN useradd --create-home --uid 1000 app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

# The app, its watchlists (indices/) and its CSVs (data/, instruments); see
# .dockerignore for what is deliberately left out.
COPY --chown=app:app . .

USER app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').read()"

CMD ["streamlit", "run", "main.py"]
