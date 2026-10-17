# Finance-Tools

A collection of financial analysis tools to help investors make data-driven decisions.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://finance-tools.streamlit.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/hirawatt?label=GitHub%20Sponsors&style=social)](https://github.com/sponsors/hirawatt)
[![Python Version](https://img.shields.io/badge/python-3.15%2B-blue)](https://www.python.org/downloads/)
[![Last Commit](https://img.shields.io/github/last-commit/hirawatt/finance-tools)](https://github.com/hirawatt/finance-tools)

## Featured Tools

### 1. Zerodha Leaderboards

Track top performers using [Verified PnL](https://support.zerodha.com/category/console/reports/other-queries/articles/verified-p-l)
**Live Demo**: [zerodha.hirawat.in](https://zerodha.hirawat.in/)

### 2. Co-Pilot: Portfolio Analyzer

An intelligent portfolio management system that provides comprehensive analysis and optimization suggestions for your investments.

#### Key Features

- Portfolio Analysis
- Risk Assessment
- Performance Tracking
- Rebalancing Suggestions
- Risk Management

## Getting Started

```bash
# Clone the repository
git clone https://github.com/hirawatt/finance-tools.git
cd finance-tools

# Install uv if you don't have it (https://docs.astral.sh/uv/)
brew install uv

# Create the environment (interpreter pinned in .python-version, deps from uv.lock)
uv sync

# Run the Streamlit app
uv run streamlit run main.py
```

`requirements.txt` is generated from `uv.lock` (`uv export`) for Streamlit
Community Cloud, which cannot read the lockfile; don't edit it by hand.

## App Structure

`main.py` is the entrypoint: it sets the page configuration once and registers
every page with [`st.navigation`](https://docs.streamlit.io/develop/api-reference/navigation/st.navigation)
and [`st.Page`](https://docs.streamlit.io/develop/api-reference/navigation/st.page),
so the sidebar's titles, icons and order all live in one place.

| Page | Module | Purpose |
| --- | --- | --- |
| Home | `main.py` | Landing page, headline stats and the data guide |
| Co-Pilot | `pages/portfolio_analysis.py` | Portfolio analytics, risk and rebalancing |
| Idea Generation | `pages/stocks_to_trade.py` | Candidate trade ideas |
| Due Diligence | `pages/surprises.py` | Surprise and unusual-activity checks |
| Index Creator | `pages/index_creator.py` | Build, edit and export watchlists |
| Stock Search | `pages/stock_search.py` | Small-cap stock screener |
| Tools | `pages/tools.py` | Percentage up/down calculator |
| About | `pages/about.py` | Credits and links |

Page modules use plain `snake_case` names (no ordering numbers or emoji
prefixes) and must not call `st.set_page_config` — the entrypoint owns the
page configuration. Pure, testable analytics helpers live in `utils/`.

## Design & theme

The look is a light "trading terminal" in the vein of Zerodha Kite, Dhan and
Screener.in: a white canvas, one confident blue accent, and numbers that read
at a glance.

- **Colours, fonts and radii** live in [`.streamlit/config.toml`](.streamlit/config.toml)
  — Inter for the interface, JetBrains Mono for code and tickers, plus
  categorical/sequential/diverging chart palettes that keep multi-series plots
  legible. Restart the app after editing it.
- **Gaps Streamlit cannot theme** (the home hero, carded metrics/tables/charts,
  the sidebar rail, the footer) live in [`utils/theme.py`](utils/theme.py) as one
  stylesheet plus small helpers — `apply_theme`, `hero`, `page_header`,
  `section_header`, `metric_row`, `card`, `feature_card`, `glyph`, `footer`.
  It is injected with `st.html`, so a page's markdown elements stay exactly as
  the page wrote them.
- **No emoji, anywhere.** Iconography is [Material Symbols](https://fonts.google.com/icons),
  the font Streamlit already bundles: `:material/<name>:` where a page is
  registered in `main.py` (and for widget `icon=` arguments), and
  `theme.glyph("<name>")` inside custom HTML. [`tests/test_style.py`](tests/test_style.py)
  fails the build if an emoji creeps back in.
- **Brand marks are committed SVGs** in `assets/` — `favicon.svg` (the browser
  tab icon, set as `page_icon`, and the collapsed sidebar mark) and `logo.svg`
  (the sidebar lockup) — so the container image carries no extra binary assets.

When adding a page, register it in `main.py` with a title and a
`:material/icon_name:` icon, and open the content with `theme.page_header(...)`
so the heading, subtitle and accent rule stay consistent.

## Run with Docker

Every push to `main` publishes a multi-architecture image (`linux/amd64` and
`linux/arm64`) to the GitHub Container Registry, so the dashboard runs without a
clone or a Python install:

```bash
docker run --rm -p 8501:8501 ghcr.io/hirawatt/finance-tools:latest
# then open http://localhost:8501
```

| Tag | Points at |
| --- | --- |
| `latest`, `main` | the tip of `main` |
| `sha-<commit>` | one specific commit |
| `v1.2.3`, `v1.2` | a release tag |

The image is self-contained: the interpreter (3.15) and every dependency come
from `uv.lock`, and with no snapshot storage configured the Co-Pilot falls back
to live Yahoo/NSE fetches. To read your own snapshot bucket, pass the
`SNAPSHOT_*` variables:

```bash
docker run --rm -p 8501:8501 \
  -e SNAPSHOT_BUCKET=my-bucket \
  -e SNAPSHOT_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com \
  -e SNAPSHOT_ACCESS_KEY=... -e SNAPSHOT_SECRET_KEY=... \
  ghcr.io/hirawatt/finance-tools:latest
```

Or mount a secrets file to also override the About-page credits:

```bash
docker run --rm -p 8501:8501 \
  -v "$PWD/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  ghcr.io/hirawatt/finance-tools:latest
```

Build it locally with `docker build -t finance-tools .`.

Watchlists you create in the app are written to `/app/indices` inside the
container, so mount that directory to keep them across restarts:

```bash
docker run --rm -p 8501:8501 -v "$PWD/indices:/app/indices" ghcr.io/hirawatt/finance-tools:latest
```

## Roadmap

### Portfolio Analyzer

- [x] Integration with [quantstats](https://github.com/ranaroussi/quantstats)
- [x] Advanced Portfolio Analytics
  - [x] Sector & Stock Weightage
  - [x] Portfolio Beta Calculation
  - [x] PE Ratio Analysis
  - [x] Correlation Matrix
- [x] Risk Management
  - [x] ASM/GSM List Monitoring
  - [x] Default Probability Assessment
  - [x] Automated Rebalancing Suggestions
- [x] Market Intelligence
  - [x] Earnings Calendar
  - [x] Price Forecasting
  - [x] Red Flag Detection

### Platform

- [x] Nightly market-data snapshot on S3-compatible storage
- [x] Dependency management with [uv](https://docs.astral.sh/uv/)
- [x] Multi-arch container image published to [GHCR](https://ghcr.io/hirawatt/finance-tools)
- [x] Streamlit-native multipage navigation with `st.navigation` / `st.Page`
- [x] Shared trading-terminal theme (brand palette, Inter/JetBrains Mono, carded metrics and tables)

## Portfolio Analysis Flow

```mermaid
flowchart TD
    A(Co-Pilot) --> B(Analyze) & C(Optimize)
    B --> D(Sector Weightage) & E(Stock Weightage)
    C --> F(Rebalance) & G(Reduce Risk) & H(Maximize Returns)
    G & H --> I["Sharpe Ratio and Treynor Ratio Comparison"]
```

## Nightly Market-Data Snapshot

The Co-Pilot's analytics would otherwise fetch every holding from Yahoo and NSE
on each cold load — roughly 60 upstream requests for a 15-stock portfolio. A
scheduled job instead fetches the curated universe once a night and publishes
Parquet files plus a manifest to S3-compatible storage; the app reads that
snapshot, and only falls back to a live fetch for symbols it does not cover
(so an arbitrary uploaded portfolio still works).

**Build it locally:**

```bash
uv run python scripts/build_snapshot.py --local ./snapshots   # local directory
uv run python scripts/build_snapshot.py --limit 5             # smoke run
```

With no `SNAPSHOT_*` configuration the snapshot is written to `./snapshots`
(git-ignored) and the app reads it when run on the same machine.

**Configure object storage** — any S3-compatible endpoint (AWS S3, Cloudflare
R2, MinIO, Backblaze B2). For the app, add a `[snapshot]` table to
`.streamlit/secrets.toml` (see `.streamlit/example.secrets.toml`); for the
nightly job, add the same values as repository secrets named `SNAPSHOT_BUCKET`,
`SNAPSHOT_PREFIX`, `SNAPSHOT_ENDPOINT_URL`, `SNAPSHOT_REGION`,
`SNAPSHOT_ACCESS_KEY` and `SNAPSHOT_SECRET_KEY`.

[`.github/workflows/nightly-snapshot.yml`](.github/workflows/nightly-snapshot.yml)
runs the job nightly at 01:00 IST (and on demand). The universe is every
watchlist in `indices/` plus the sample portfolio — currently ~220 symbols;
edit `utils/snapshot.py::build_universe` to widen it.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support the Project

If you find this project useful, consider supporting its development:

- [GitHub Sponsors](https://github.com/sponsors/hirawatt)
- <a href="https://www.buymeacoffee.com/hirawat" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="100" height="25" ></a>

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
