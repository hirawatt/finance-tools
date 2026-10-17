"""Credits page.

Reads the credit links from the ``[credits]`` secrets table when one is
configured (see ``.streamlit/example.secrets.toml``) and otherwise falls back to
the repository's own links, so the app also runs with no secrets at all — the
published container image ships without any.
"""

import streamlit as st

from utils import theme

FALLBACK_CREDITS = {
    "website": "https://github.com/hirawatt/finance-tools",
    "name": "Hirawat",
    "buymeacoffee": (
        '<a href="https://www.buymeacoffee.com/hirawat" target="_blank">'
        '<img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" '
        'alt="Buy Me A Coffee" width="100" height="25"></a>'
    ),
}


def credits():
    """Merge the optional ``[credits]`` secrets table over the fallbacks."""
    try:
        table = dict(st.secrets.get("credits") or {})
    except Exception:  # no secrets file, or running outside Streamlit
        table = {}
    return {
        key: table.get(key) or fallback for key, fallback in FALLBACK_CREDITS.items()
    }


_credits = credits()
website = _credits["website"]
name = _credits["name"]
buymeacoffee = _credits["buymeacoffee"]


def credits_panel():
    """The credits expander: who built this, and how to support it.

    Named for what it shows rather than "footer", which is the app-wide
    ``theme.footer()`` strip. The HTML goes through :func:`st.html` (the modern
    way to render markup), so the page's markdown elements stay reserved for
    copy, as in :mod:`utils.theme`.
    """
    with st.expander("Credits", expanded=True):
        st.html(
            '<div style="text-align: center">Made with care by '
            '<a href="{}">{}</a></div>'.format(website, name)
        )
        st.html(buymeacoffee)


def main():
    theme.page_header(
        "About",
        "Credits, links and the people behind The Trading Dashboard.",
    )
    credits_panel()

if __name__ == "__main__":
    main()
