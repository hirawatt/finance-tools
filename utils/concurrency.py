"""Concurrency and retry helpers for the network-bound fetches.

The market-data providers (Yahoo Finance via ``yfinance``, NSE's JSON
endpoints) are queried once per symbol. Doing that sequentially makes a
portfolio load slow, so callers fan the per-symbol work out over a small
thread pool and retry transient failures with exponential backoff.

Both helpers are pure apart from the injectable ``sleep`` and the callable they
are handed, so they can be unit-tested without touching the network.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")
R = TypeVar("R")

# Keep the fan-out modest: Yahoo throttles aggressive clients, so a handful of
# workers with backoff is both faster and more reliable than a wide burst.
DEFAULT_MAX_WORKERS = 6
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF = 0.5


def retry_call(
    func: Callable[[], R],
    attempts: int = DEFAULT_ATTEMPTS,
    backoff: float = DEFAULT_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> R:
    """Call ``func`` and retry it with exponential backoff on any exception.

    Re-raises the last error once ``attempts`` have been exhausted.
    """
    attempts = max(1, attempts)
    last: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if attempt < attempts:
                sleep(backoff * 2 ** (attempt - 1))
    raise last  # type: ignore[misc]


def parallel_map(
    func: Callable[[T], R],
    items: Sequence[T],
    max_workers: int = DEFAULT_MAX_WORKERS,
    attempts: int = DEFAULT_ATTEMPTS,
) -> List[Tuple[T, Optional[R], Optional[BaseException]]]:
    """Apply ``func`` to ``items`` concurrently, preserving input order.

    Each call is wrapped in :func:`retry_call`. A failure on one item never
    aborts the batch: the result carries one ``(item, value, error)`` triple per
    input, with ``value`` set to ``None`` and ``error`` populated when the item
    could not be processed, so callers can report what was skipped.
    """
    items = list(items)
    if not items:
        return []

    def work(item: T) -> Tuple[T, Optional[R], Optional[BaseException]]:
        try:
            return item, retry_call(lambda: func(item), attempts=attempts), None
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            return item, None, exc

    if len(items) == 1 or max_workers <= 1:
        return [work(item) for item in items]

    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        return list(pool.map(work, items))
