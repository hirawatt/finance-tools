"""Import Portfolio — bring a broker's holdings into the Co-Pilot.

Four beats: drop a file, confirm which broker it came from, resolve the symbols
and values, then either use the portfolio for this session or save it locally.

Privacy is the default: the upload is read in memory, nothing is uploaded
anywhere, and nothing reaches disk unless the user presses *Save locally*
(``portfolios/``, which is git-ignored).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from utils import brokers, charts, holdings, portfolio_store, theme
from utils.brokers import kite
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


@st.cache_resource(show_spinner=False)
def kite_config() -> kite.KiteConfig:
    """The Kite app credentials from secrets/env; unconfigured by default."""
    try:
        secrets = st.secrets.to_dict()
    except Exception:  # no secrets file, or running outside Streamlit
        secrets = {}
    return kite.KiteConfig.from_secrets(secrets)


@st.cache_resource(show_spinner=False)
def kite_tokens() -> kite.TokenStore:
    """The owner-only access-token store on this machine."""
    return kite.TokenStore()


def _profile_options() -> Dict[str, brokers.BrokerProfile]:
    """Built-in brokers plus any mapping the user has saved."""
    options: Dict[str, brokers.BrokerProfile] = dict(brokers.PROFILES_BY_NAME)
    for name, mapping in profile_library.saved_profiles().items():
        options[name] = profile_library.profile_from_mapping(name, mapping)
    return options


#: Session key holding the statement that last opened, with the digest of the
#: bytes it was read from. Deliberately not the read button's key, which lives in
#: session state as a bool.
CAS_READ = "import-cas-statement"


@st.cache_data(show_spinner=False, max_entries=16)
def _detect_upload(data: bytes, filename: str) -> Optional[brokers.BrokerProfile]:
    """The broker whose signature the upload carries, parsed once per file."""
    return brokers.detect_profile(data, filename)


@st.cache_data(show_spinner=False, max_entries=16)
def _preview_upload(data: bytes, filename: str, profile_name: str) -> pd.DataFrame:
    """The raw table for the mapping screen, parsed once per file and format."""
    return brokers.preview_table(data, filename, _profile_options().get(profile_name))


@st.cache_data(show_spinner="Reading the file…", max_entries=8)
def _parse_upload(
    data: bytes,
    filename: str,
    profile_name: str,
    mapping: Optional[Tuple[Tuple[str, str], ...]] = None,
) -> brokers.BrokerImport:
    """Parse and resolve one upload, cached per file, format and column mapping.

    The portfolio name is deliberately not part of the key: it is applied
    afterwards by :func:`_with_client`, so typing it does not re-read the file.
    """
    profile = _profile_options().get(profile_name) or brokers.GENERIC
    if mapping is not None:
        profile = profile_library.profile_from_mapping(profile_name, dict(mapping))
    return brokers.import_holdings(data, filename, profile=profile, master=symbol_master())


def _with_client(result: brokers.BrokerImport, client: str) -> brokers.BrokerImport:
    """The same import, stamped with the portfolio name the user typed."""
    if not client:
        return result
    return replace(result, holdings=result.holdings.assign(Client=client))


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
        if columns[1].button("Use", key=f"use-{name}", icon=":material/check:"):
            frame = portfolio_store.load_saved(name)
            if frame is not None:
                portfolio_store.set_active(holdings.to_core(frame), label=name)
                # A toast outlives the rerun; an alert rendered now would not.
                st.toast(
                    f"{name} is now the active portfolio.",
                    icon=":material/check_circle:",
                )
                st.rerun()
        if columns[2].button("Delete", key=f"delete-{name}", icon=":material/delete:"):
            portfolio_store.delete_saved(name)
            st.toast(f"Deleted {name}.", icon=":material/delete:")
            st.rerun()


def _render_result(result: brokers.BrokerImport, client: str) -> None:
    """Warnings, then the confirm beat — the tail both import paths share."""
    named = _with_client(result, client)
    for warning in named.warnings:
        st.warning(warning)
    _render_preview(named, client)


def _import_statement(data: bytes, filename: str) -> None:
    """A depository CAS PDF — the client book from a single file.

    Decrypting and parsing a statement costs a pass over every page, so it runs
    once, when *Read statement* is pressed, and the result is kept for the
    session: re-reading on each rerun would re-parse the PDF on every keystroke
    in the password box.
    """
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

    digest = (filename, hashlib.sha256(data).hexdigest())
    read = st.session_state.get(CAS_READ)
    if read is not None and read["file"] == digest:
        _render_result(read["result"], client)
        return

    if not st.button(
        "Read statement",
        type="primary",
        icon=":material/lock_open:",
        key="import-cas-read",
    ):
        st.caption(
            "Enter the password the depository set, then read the statement to "
            "preview its holdings."
        )
        return

    parsed = brokers.import_holdings(
        data, filename, master=symbol_master(), password=password
    )
    if parsed.holdings.empty:
        # A wrong password must leave the button in place for another attempt.
        _render_result(parsed, client)
        return

    st.session_state[CAS_READ] = {"file": digest, "result": parsed}
    _render_result(parsed, client)


def _render_kite() -> None:
    """Zerodha Kite Connect: connect once, then import without a file.

    Rendered only when the deployment carries Kite credentials, so a public
    instance never offers a connection it cannot make.
    """
    config = kite_config()
    if not config.configured:
        return

    theme.section_header(
        "Zerodha Kite Connect",
        "Connect once and pull holdings straight from the account — no file.",
    )
    store = kite_tokens()

    token_param = st.query_params.get("request_token")
    request_token = token_param[0] if isinstance(token_param, list) else token_param
    if request_token:
        try:
            session = kite.exchange_request_token(config, request_token)
        except Exception as error:
            st.error(f"Could not finish the Kite login: {error}")
        else:
            store.save(session)
            st.query_params.clear()
            st.rerun()
        return

    session = store.load()
    if session is None or not session.is_fresh():
        st.link_button("Connect Zerodha", config.login_url(), icon=":material/open_in_new:")
        st.caption(
            "You sign in on Kite's own page and the dashboard never sees your "
            "password. The access token is written to this machine, readable only "
            "by its owner, and expires each morning."
        )
        return

    st.success(
        f"Connected as **{session.user_id or 'Zerodha account'}** · token valid "
        f"until {session.expires_at():%d %b, %H:%M} IST."
    )
    client = st.text_input("Portfolio name", value="Zerodha account", key="kite_client")
    if st.button("Import holdings from Zerodha", type="primary", key="kite-import"):
        try:
            frame = kite.fetch_holdings(session)
        except Exception as error:  # an expired or revoked token, or a Kite outage
            st.error(f"Kite refused the request: {error}")
            return
        result = brokers.import_records(
            frame,
            profile_name="Zerodha (Kite Connect)",
            source=session.user_id or "Zerodha",
            master=symbol_master(),
            client=client,
        )
        _render_result(result, client)


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

    _render_kite()

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

    detected = _detect_upload(data, filename)
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
    table = _preview_upload(data, filename, chosen_name)

    mapping: Optional[Dict[str, str]] = None
    if chosen_name == "Generic" or profile.signature == ():
        mapping = _mapping_editor(
            table, brokers.guess_mapping(table, profile), key="import-map"
        )
        if st.button("Save this mapping for next time", key="import-save-map"):
            saved = profile_library.save_profile(client or "My broker", mapping)
            if saved is not None:
                st.success(f"Saved the mapping as **{saved.stem}**; it is now in the broker list.")
            else:
                st.warning("Could not save the mapping — map a symbol or quantity column first.")

    try:
        result = _parse_upload(
            data,
            filename,
            chosen_name,
            None if mapping is None else tuple(sorted(mapping.items())),
        )
    except Exception as error:  # a malformed file should not break the page
        st.error(f"Could not read the file: {error}")
        return

    _render_result(result, client)


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

    if len(frame) > 1 and frame["Current Value"].sum() > 0:
        by_holding = (
            frame.groupby("Symbol")["Current Value"].sum().sort_values(ascending=False)
        )
        st.subheader("Allocation preview")
        theme.chart(
            charts.donut(
                by_holding,
                max_slices=8,
                center_title="Current value",
                center_value=f"₹{frame['Current Value'].sum():,.0f}",
                value_fmt="₹{:,.0f}",
                height=320,
            ),
            alt="How the imported portfolio's current value splits across its largest holdings",
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

    st.page_link(
        Path(__file__).with_name("portfolio_analysis.py"),
        label="Go to the Co-Pilot",
    )


if __name__ == "__main__":
    main()
