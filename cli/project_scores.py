"""Project ``v_score_snapshot`` into dated ``ingest`` graphs (T-031).

uv run python cli/project_scores.py            # dry run: read, check, and SHACL-validate the batches
uv run python cli/project_scores.py --write    # also append them to the store through the ingest gate

Reads ``SQL_FINANCIAL_DB`` and ``SQL_UNIVERSE_DB`` (``.env``). The late-key file persists, between
runs, the rows the boundary delayed; ``--late-keys`` names it (default: not kept).
Exit status: 0 on success, 1 if the boundary stopped the run or the gate refused a graph.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from etl import config
from kg_store.graphdb import GraphDB, GraphDBError
from projection.boundary import BoundaryError
from projection.score_snapshots import run, universe_symbols
from projection.source import FinancialSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="append the batches to the store")
    parser.add_argument("--late-keys", type=Path, help="file that keeps delayed rows' keys")
    parser.add_argument("--run-day", default=datetime.date.today().isoformat(), help="YYYY-MM-DD")
    args = parser.parse_args()

    db = FinancialSource.open(config.financial_db_path())
    try:
        assets = universe_symbols(config.universe_db_path())
        store = GraphDB.from_env() if args.write else None
        result = run(db, assets, store, args.run_day, late_keys_path=args.late_keys)
    except BoundaryError as exc:
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
