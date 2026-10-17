"""Import Portfolio — bring a broker's holdings into the Co-Pilot.

Four beats: drop a file, confirm which broker it came from, resolve the symbols
and values, then either use the portfolio for this session or save it locally.

Privacy is the default: the upload is read in memory, nothing is uploaded
anywhere, and nothing reaches disk unless the user presses *Save locally*
(``portfolios/``, which is git-ignored).
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import streamlit as st

from utils import brokers, holdings, portfolio_store, theme
from utils.brokers import profiles as profile_library

#: The fields the mapping editor exposes — the rest of the canonical schema is
#: derived. Symbol/ISIN/Company identify the stock; quantity and prices value it.
MAPPABLE = (
    "Symbol",
    "ISIN",
    "Company",
    "Total Quantity",
    "Average Price",
    "Current Price",
)

PREVIEW_COLUMNS = (
    "Symbol",
    "Company",
    "ISIN",
    "Total Quantity",
    "Average Price",
    "Current Price",
    "Invested Value",
    "Current Value",
    "Match",
)

PREVIEW_FORMATS = {
    "Total Quantity": "{:,.0f}",
    "Average Price": "₹{:,.2f}",
    "Current Price": "₹{:,.2f}",
    "Invested Value": "₹{:,.0f}",
    "Current Value": "₹{:,.0f}",
}


@st.cache_resource(show_spinner=False)
def symbol_master() -> holdings.SymbolMaster:
    """The ISIN/symbol/name lookup, built once per process from committed files."""
    return holdings.SymbolMaster.from_paths()


def _profile_options() -> Dict[str, brokers.BrokerProfile]:
    """Built-in brokers plus any mapping the user has saved."""
    options: Dict[str, brokers.BrokerProfile] = dict(brokers.PROFILES_BY_NAME)
    for name, mapping in profile_library.saved_profiles().items():
        options[name] = profile_library.profile_from_mapping(name, mapping)
    return options


def _number_column(pattern: str) -> "st.column_config.NumberColumn":
    return st.column_config.NumberColumn(format=theme.printf_format(pattern))


def _mapping_editor(
    table: pd.DataFrame, defaults: Dict[str, str], key: str
) -> Dict[str, str]:
    """A selectbox per target field, defaulted to the best guess."""
    choices = [""] + [str(column) for column in table.columns]
    mapping: Dict[str, str] = {}
    st.caption(
        "Point each field at the column it lives in. Symbol or ISIN and quantity "
        "are what the analytics need most."
    )
    grids = st.columns(3)
    for index, target in enumerate(MAPPABLE):
        default = defaults.get(target, "")
        position = choices.index(default) if default in choices else 0
        with grids[index % 3]:
            mapping[target] = st.selectbox(
                target, choices, index=position, key=f"{key}-{target}"
            )
    return mapping


def _render_export_help() -> None:
    """Per-broker 'how to export' cards, shown before a file is dropped."""
    theme.section_header(
        "Where to get the file",
        "Download the holdings statement from your broker, then drop it above.",
    )
    for profile in brokers.PROFILES:
        with st.expander(profile.name):
            st.markdown(profile.export_steps)
            if profile.export_url:
                st.markdown(f"[Open {profile.name}]({profile.export_url})")

    with st.expander("Depository CAS — every broker at once"):
        st.markdown(
            "A Consolidated Account Statement from [CDSL](https://www.cdslindia.com/) "
            "or [NSDL](https://nsdl.co.in/) lists every demat account and broker in "
            "one PDF. It is password-protected, usually by your PAN plus date of "
            "birth. A CAS carries no purchase price, so invested value and P&L read "
            "flat — the positions and weights are still right."
        )


def _render_saved() -> None:
    """Portfolios saved to this machine, with a one-click load."""
    saved = portfolio_store.list_saved()
    if not saved:
        return
    theme.section_header(
        "Saved locally",
        "Only on this machine, under the git-ignored portfolios/ directory.",
    )
    for name in saved:
        columns = st.columns([4, 1, 1])
        columns[0].markdown(f"**{name}**")
        if columns[1].button("Use", key=f"use-{name}"):
            frame = portfolio_store.load_saved(name)
            if frame is not None:
                portfolio_store.set_active(holdings.to_core(frame), label=name)
                st.success(f"**{name}** is now the active portfolio.")
                st.rerun()
        if columns[2].button("Delete", key=f"delete-{name}"):
            portfolio_store.delete_saved(name)
            st.rerun()


def _import_statement(data: bytes, filename: str) -> None:
    """A depository CAS PDF — the client book from a single file."""
    st.info(
        "Reading a depository **CAS** statement: one PDF covers every broker and "
        "demat account at once."
    )
    with st.container(horizontal=True, vertical_alignment="bottom"):
        password = st.text_input(
            "Statement password",
            type="password",
            key="import-cas-password",
            help="Usually your PAN plus date of birth, as the depository set it.",
        )
        client = st.text_input("Portfolio name", value="My portfolio", key="import_client")

    result = brokers.import_holdings(
        data, filename, master=symbol_master(), client=client, password=password
    )
    for warning in result.warnings:
        st.warning(warning)
    _render_preview(result, client)


def main() -> None:
    theme.page_header(
        "Import Portfolio",
        "Bring holdings from Zerodha, Groww, Dhan or Angel One — any spreadsheet "
        "with a symbol column, or a depository CAS PDF.",
    )
    st.caption(
        "Your file is read in memory for this session. It is not uploaded "
        "anywhere, and nothing is written to disk unless you press *Save locally*."
    )

    uploaded = st.file_uploader(
        "Drop a holdings export",
        type=["xlsx", "xls", "csv", "pdf"],
        help=(
            "Zerodha Console, Groww, Dhan and Angel One exports are detected "
            "automatically; a depository CAS statement comes as a PDF."
        ),
    )
    if uploaded is None:
        _render_export_help()
        _render_saved()
        return

    data = uploaded.getvalue()
    filename = uploaded.name

    if filename.lower().endswith(".pdf"):
        _import_statement(data, filename)
        return

    detected = brokers.detect_profile(data, filename)
    options = _profile_options()

    default_name = detected.name if detected and detected.name in options else "Generic"
    with st.container(horizontal=True, vertical_alignment="bottom"):
        chosen_name = st.selectbox(
            "Broker format",
            list(options),
            index=list(options).index(default_name),
            key="import_broker",
        )
        client = st.text_input("Portfolio name", value="My portfolio", key="import_client")

    if detected is not None:
        st.success(f"Detected **{detected.name}** from the file's headers.")
    else:
        st.info(
            "Could not identify the broker from the headers — pick the format, or "
            "map the columns below."
        )

    profile = options[chosen_name]
    table = brokers.preview_table(data, filename, profile)

    if chosen_name == "Generic" or profile.signature == ():
        mapping = _mapping_editor(
            table, brokers.guess_mapping(table, profile), key="import-map"
        )
        profile = profile_library.profile_from_mapping(chosen_name, mapping)
        if st.button("Save this mapping for next time", key="import-save-map"):
            saved = profile_library.save_profile(client or "My broker", mapping)
            if saved is not None:
                st.success(f"Saved the mapping as **{saved.stem}**; it is now in the broker list.")
            else:
                st.warning("Could not save the mapping — map a symbol or quantity column first.")

    try:
        result = brokers.import_holdings(
            data,
            filename,
            profile=profile,
            master=symbol_master(),
            client=client,
        )
    except Exception as error:  # a malformed file should not break the page
        st.error(f"Could not read the file: {error}")
        return

    for warning in result.warnings:
        st.warning(warning)

    _render_preview(result, client)


def _render_preview(result: brokers.BrokerImport, client: str) -> None:
    """The confirm beat: counts, the resolved table, and the two actions."""
    frame = result.holdings
    if frame.empty:
        st.error("No holdings rows were found in the file.")
        return

    summary = result.summary
    matched = summary.get("alias", 0) + summary.get("isin", 0) + summary.get("symbol", 0) + summary.get("name", 0)
    theme.metric_row(
        (
            ("Holdings", len(frame)),
            ("Symbols resolved", f"{matched} / {len(frame)}"),
            ("Invested", f"₹{frame['Invested Value'].sum():,.0f}"),
            ("Current value", f"₹{frame['Current Value'].sum():,.0f}"),
        )
    )

    if summary.get("isin"):
        st.caption(
            f"{summary['isin']} held through the **ISIN** — the same key at every "
            "broker, so re-importing from a second broker merges cleanly."
        )

    preview = result.resolved.reindex(columns=list(PREVIEW_COLUMNS)).rename(
        columns={"Match": "Matched by"}
    )
    st.dataframe(
        preview,
        hide_index=True,
        column_config={
            column: _number_column(pattern)
            for column, pattern in PREVIEW_FORMATS.items()
        },
        alt="Imported holdings with resolved symbols and values",
    )

    needs_attention = holdings.unresolved(result.resolved)
    if not needs_attention.empty:
        st.warning(
            f"{len(needs_attention)} row(s) could not be matched to an NSE symbol."
        )
        st.dataframe(
            needs_attention.reindex(columns=["Symbol", "ISIN", "Company"]),
            hide_index=True,
            alt="Rows whose symbol could not be resolved",
        )

    with st.container(horizontal=True):
        if st.button("Use this portfolio", type="primary", key="import-use"):
            portfolio_store.set_active(holdings.to_core(frame), label=client or result.source)
            st.success("Loaded. Open the Co-Pilot to analyse it.")

        if st.button("Save locally", key="import-save"):
            try:
                portfolio_store.save_local(client or result.source, frame)
                st.success(f"Saved under **portfolios/{client or result.source}**.")
            except Exception as error:  # e.g. an unnamed portfolio
                st.error(f"Could not save: {error}")

    st.page_link("pages/portfolio_analysis.py", label="Go to the Co-Pilot")


if __name__ == "__main__":
    main()
