# Tool-directory logos

Brand marks for the cards on the **Tool Directory** page
(`pages/tool_directory.py`). Each file is fetched once from the vendor's own
site (or from Google's live favicon service where the site exposes no larger
mark) and committed here, so the app and its container image carry no runtime
dependency on those third parties.

Every mark remains the trademark of its owner and is used only to identify the
linked service. Colours, fonts and shapes are the vendors' own.

| File | Source | Notes |
| --- | --- | --- |
| `tradingeconomics.svg` | `tradingeconomics.com/favicon.svg` | Vector mark |
| `toggle.png` | Google favicon service (`toggle.ai`) | 32px, largest available |
| `intradayscreener.svg` | `intradayscreener.com/assets/images/new_logo.svg` | Wordmark |
| `harmoney.png` | `inferedge.com/favicon.ico` | Harmoney now trades as InferEdge |
| `spidersoftware.png` | `spidersoftwareindia.com/images/Spidersoftware_logo.png` | Wordmark |
| `3commas.png` | `3commas.io/apple-touch-icon.png` | 180px |
| `marketbeat.png` | `marketbeat.com/apple-touch-icon-180x180.png` | 180px |
| `stocksemoji.png` | `stocksemoji.com/logo.png` | Wordmark |
| `momoindiascreener.png` | Google favicon service (`momoindiascreener.in`) | 256px |
| `scanx.png` | `scanx.trade/favicon.ico` | Largest embedded size |
| `punch.png` | Google favicon service (`punch.trade`) | 192px |
| `orderblock.svg` | `order-block.com/static/img/favicon.svg` | Vector mark |

AnaStrat, Swift Journal and PaperTrade expose no reachable brand mark (the
domains are parked or dead), so their cards fall back to an initials tile
rendered by `theme.tool_grid`.

Fetched on 2026-10-17. Regenerate a mark by downloading the source URL again and
overwriting the file; no build step is involved.
