"""Build the nightly market-data snapshot.

Fetches the curated symbol universe once and publishes Parquet blobs plus a
manifest to S3-compatible storage, so the app does not have to touch Yahoo or
NSE on the request path. See :mod:`utils.snapshot` for the format.

Typical use::

    python scripts/build_snapshot.py                  # the configured store
    python scripts/build_snapshot.py --limit 5        # quick smoke run
    python scripts/build_snapshot.py --local ./snapshots

Storage comes from the ``SNAPSHOT_*`` environment variables (bucket, prefix,
endpoint, region, credentials). Without a bucket the snapshot is written to a
local directory, which is what local development wants.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Sequence

# Allow ``python scripts/build_snapshot.py`` from a checkout without an install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import snapshot  # noqa: E402

LOGGER = logging.getLogger("build_snapshot")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--period", default=snapshot.DEFAULT_PERIOD,
                        help="price history window to snapshot (default: %(default)s)")
    parser.add_argument("--benchmark", default=snapshot.BENCHMARK_KEY,
                        help="benchmark ticker stored alongside the prices")
    parser.add_argument("--index-dir", default=str(snapshot.DEFAULT_INDEX_DIR),
                        help="directory of curated watchlists defining the universe")
    parser.add_argument("--holdings", default=str(snapshot.DEFAULT_HOLDINGS),
                        help="holdings export to add to the universe")
    parser.add_argument("--local", metavar="DIR",
                        help="write to this directory instead of object storage")
    parser.add_argument("--limit", type=int,
                        help="snapshot only the first N symbols (smoke runs)")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _universe(args: argparse.Namespace) -> List[str]:
    universe = snapshot.build_universe(args.index_dir, args.holdings)
    if args.limit is not None:
        universe = universe[: max(0, args.limit)]
    return universe


def _store(args: argparse.Namespace):
    if args.local:
        return snapshot.LocalStore(Path(args.local))
    return snapshot.SnapshotConfig.from_env().store()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")

    universe = _universe(args)
    if not universe:
        LOGGER.error("empty universe; check --index-dir and --holdings")
        return 1

    store = _store(args)
    LOGGER.info(
        "snapshotting %d symbols over %s into %s",
        len(universe), args.period, type(store).__name__,
    )

    frames, failures = snapshot.fetch_universe_data(
        universe, period=args.period, benchmark=args.benchmark
    )
    if not frames:
        LOGGER.error("every dataset failed: %s", failures)
        return 1

    if failures:
        # A partial snapshot is still worth publishing; the app falls back to
        # live fetches for whatever is missing.
        LOGGER.warning("failed datasets: %s", failures)

    manifest = snapshot.write_snapshot(
        store,
        frames,
        period=args.period,
        benchmark=args.benchmark,
        universe=universe,
        failures=failures,
    )

    LOGGER.info("wrote snapshot generated_at=%s", manifest["generated_at"])
    for name, info in manifest["datasets"].items():
        LOGGER.info("  %-13s %6d rows", name, info["rows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
