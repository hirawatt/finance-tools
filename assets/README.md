# Brand assets

The app's own marks and the README's images. Everything here is committed, so
the app and its container image fetch no brand file at runtime.

| File | Role | Used by |
| --- | --- | --- |
| `favicon.svg` | Browser-tab icon and collapsed-sidebar mark | `st.set_page_config(page_icon=...)`, `st.logo(icon_image=...)` in `main.py` |
| `logo.svg` | Sidebar lockup | `st.logo(...)` in `main.py` |
| `app-icon.svg` | High-resolution square mark (512px) | The home hero's brand lockup (`theme.hero(mark=...)`) |
| `hero-graphic.svg` | Decorative analytics illustration | The home hero's right column (`theme.hero(graphic=...)`) |
| `banner.svg` | README header, 1200x320: mark, name, byline and tagline | Source for `banner.png` |
| `banner.png` | `banner.svg` rendered at 1600px for GitHub | The README header |
| `social-card.svg` | 1200x630 link-preview card | Link previews and other listings |
| `screenshots/home.png` | The home page as it renders | The README's "What it looks like" section |

The palette, type stack and mark geometry follow `utils/theme.py` (`PALETTE`) and
`.streamlit/config.toml`: accent `#1F6FEB`, blue ramp `#3B82F6` to `#1D4ED8`,
ink `#0B1220`, muted `#64748B`, hairline `#E2E8F0`, gain/loss `#12B886`/`#E5484D`.
There are no emoji anywhere (`tests/test_style.py` enforces it), and the SVGs
are standalone — no external fonts, scripts or inlined images.

`theme.hero` inlines `app-icon.svg` and `hero-graphic.svg` as data URIs, so a
copy change means editing the file, nothing else.

## Regenerating the raster files

There is no build step; both were rendered once with headless Chromium and
committed. To redo them, render the SVG at its viewBox aspect ratio and
screenshot it — for example with Playwright:

```bash
npx playwright screenshot --viewport-size=1600,427 \
  file://$PWD/assets/banner.svg assets/banner.png
```

For `screenshots/home.png`, run the app (`uv run streamlit run main.py`) and
capture a 1440x1278 viewport at `deviceScaleFactor: 1` — the hero, the headline
stats, the workflow strip and the first row of tool cards.
