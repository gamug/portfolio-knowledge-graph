"""Project ``v_score_snapshot`` into dated ``ingest`` graphs (T-031).

uv run python cli/project_scores.py            # dry run: read, check, and SHACL-validate the batches
uv run python cli/project_scores.py --write    # also append them to the store through the ingest gate

Reads ``SQL_FINANCIAL_DB`` and ``SQL_UNIVERSE_DB`` (``.env``). The late-key file persists, between
runs, the rows the boundary delayed; ``--late-keys`` names it (default: not kept). ``--run-day``
(``YYYY-MM-DD``, default today in UTC) dates the cycle lanes' graphs.
Exit status: 0 on success, 1 if the boundary or the projection stopped the run or the gate refused
a graph, 2 on a bad argument.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from etl import config
from kg_store.graphdb import GraphDB, GraphDBError
from projection.boundary import BoundaryError
from projection.score_snapshots import ProjectionError, run, universe_symbols
from projection.source import FinancialSource


def run_day(text: str) -> str:
    """``--run-day``: an ISO date, checked here rather than at the gate."""
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a YYYY-MM-DD date") from None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--write", action="store_true", help="append the batches to the store")
    parser.add_argument("--late-keys", type=Path, help="file that keeps delayed rows' keys")
    parser.add_argument(
        "--run-day",
        type=run_day,
        default=datetime.datetime.now(datetime.UTC).date().isoformat(),
        help="YYYY-MM-DD (default: today in UTC)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    db = FinancialSource.open(config.financial_db_path())
    try:
        assets = universe_symbols(config.universe_db_path())
        store = GraphDB.from_env() if args.write else None
        result = run(db, assets, store, args.run_day, late_keys_path=args.late_keys)
    except (BoundaryError, ProjectionError) as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(result.summary())
    return 1 if result.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
