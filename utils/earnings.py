"""Upcoming earnings dates for portfolio holdings.

Parsing is pure; only :func:`fetch_earnings_calendar` touches the network
(Yahoo Finance's per-ticker calendar).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

import pandas as pd

from utils.market_data import to_ticker

EARNINGS_COLUMNS = ["Symbol", "Date", "Days away", "EPS estimate", "Revenue estimate"]


def _as_date(value) -> Optional[date]:
    """Coerce the assorted date shapes yfinance returns into a ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except ValueError:
            return None
    return None


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=EARNINGS_COLUMNS)


def parse_next_earnings(symbol: str, calendar, today: Optional[date] = None) -> Optional[dict]:
    """Pick a symbol's next earnings date on or after ``today`` from its calendar."""
    today = today or date.today()
    if not isinstance(calendar, dict):
        return None

    raw = calendar.get("Earnings Date") or []
    if isinstance(raw, (date, datetime, str)):
        raw = [raw]

    future = sorted(
        d for d in (_as_date(value) for value in raw) if d is not None and d >= today
    )
    if not future:
        return None

    next_date = future[0]
    return {
        "Symbol": symbol,
        "Date": next_date,
        "Days away": (next_date - today).days,
        "EPS estimate": calendar.get("Earnings Average"),
        "Revenue estimate": calendar.get("Revenue Average"),
    }


def fetch_earnings_calendar(
    symbols: Iterable[str], today: Optional[date] = None
) -> pd.DataFrame:
    """Fetch each symbol's next earnings date, sorted soonest first."""
    import yfinance as yf

    today = today or date.today()
    clean = [s for s in dict.fromkeys(str(s).strip() for s in symbols) if s]

    rows = []
    for symbol in clean:
        try:
            calendar = yf.Ticker(to_ticker(symbol)).calendar
        except Exception:
            continue
        parsed = parse_next_earnings(symbol, calendar, today)
        if parsed:
            rows.append(parsed)

    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows, columns=EARNINGS_COLUMNS).sort_values("Date").reset_index(drop=True)


def upcoming(frame: Optional[pd.DataFrame], within_days: int = 90) -> pd.DataFrame:
    """Keep only earnings falling within the next ``within_days``."""
    if frame is None or frame.empty:
        return _empty_frame()
    filtered = frame[frame["Days away"] <= within_days]
    return filtered.sort_values("Days away").reset_index(drop=True)
