"""Project ``v_score_snapshot`` into dated ``ingest`` graphs (T-031).

uv run python cli/project_scores.py            # dry run: read, check, and SHACL-validate the batches
uv run python cli/project_scores.py --write    # also append them to the store through the ingest gate

Reads ``SQL_FINANCIAL_DB`` and ``SQL_UNIVERSE_DB`` (``.env``). The late-key file persists, between
runs, the rows the boundary delayed; ``--late-keys`` names it (default: not kept). Beside it
(``late.json`` -> ``late.lost.json``) a write keeps the rows already listed as lost, so a later run
lists only new losses (without a late-key file, every loss is listed every run). The key files
belong to one repository: a write to any repository other than production keeps its own pair in a
folder named for it, beside the given file (``keys/late.json`` -> ``keys/<repository>/late.json``
and ``keys/<repository>/late.lost.json``), so a replay never settles or hides production's rows.

``--run-day`` (``YYYY-MM-DD``, default today in UTC) dates the cycle lanes' graphs and is the day
the run sees upstream as of: a row not yet available on it is left for a later run. A day after
today is refused. A past day is a replay: ``--write`` with it needs ``--replay``, ``--replay`` needs
``--write``, and it never writes to the production repository (``KG_REPOSITORY=portfolio``), whose
graphs record what was loaded on which day.
A dry run does not consult the store, so it cannot see which graphs already exist.
Exit status: 0 on success; 1 if the boundary or the projection stopped the run, the source could
not be read, the store failed or the gate refused a graph; 2 on a bad argument. Rows lost (listed
under ``lost``) do not change it.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from etl import config
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError
from projection.boundary import BoundaryError
from projection.score_snapshots import (
    ProjectionError,
    RunResult,
    StoreInterrupted,
    run,
    universe_symbols,
)
from projection.source import FinancialSource


def today() -> str:
    """Today in UTC: the default run day, and the latest one allowed."""
    return datetime.datetime.now(datetime.UTC).date().isoformat()


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
        "--run-day", type=run_day, help="YYYY-MM-DD, not after today (default: today in UTC)"
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="with --write: allow a past run day (never to the production repository)",
    )
    args = parser.parse_args(argv)
    now = today()
    if args.run_day is None:
        args.run_day = now
    if args.run_day > now:
        parser.error(f"--run-day {args.run_day} is after today ({now} UTC)")
    if args.replay and not args.write:
        parser.error("--replay only matters with --write (a dry run with a past day needs no flag)")
    if args.write and args.run_day < now and not args.replay:
        parser.error(f"--run-day {args.run_day} is in the past: --write with it needs --replay")
    return args


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """The store a ``--write`` appends to; a replay aimed at production exits with status 2."""
    if not args.write:
        return None
    store = GraphDB.from_env()
    if args.replay and store.repository == PRODUCTION_REPOSITORY:
        print(
            f"--replay never writes to the production repository ({PRODUCTION_REPOSITORY}); "
            "set KG_REPOSITORY to a replay repository",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


_REPOSITORY_ID = re.compile(r"[A-Za-z0-9_-]+")


def key_file(path: Path | None, store: GraphDB | None) -> Path | None:
    """The late-key file of the repository written to: ``path`` itself for production (and a dry
    run), and for any other the same name in a folder named for the repository, beside ``path``
    (created if missing). Its lost-key file lands beside it too, so no file of one repository can
    share a name with a file of another, whatever the repository or ``path`` is called."""
    if path is None or store is None or store.repository == PRODUCTION_REPOSITORY:
        return path
    if not _REPOSITORY_ID.fullmatch(store.repository):
        print(f"KG_REPOSITORY {store.repository!r} cannot name a key folder", file=sys.stderr)
        raise SystemExit(2)
    own = path.parent / store.repository / path.name
    own.parent.mkdir(parents=True, exist_ok=True)
    return own


def project(args: argparse.Namespace) -> RunResult:
    """Open the store and the sources, then run; nothing is read before the store is settled."""
    store = open_store(args)
    keys = key_file(args.late_keys, store)
    if keys != args.late_keys:
        print(f"key files of repository {store.repository if store else ''}: {keys}")
    db = FinancialSource.open(config.financial_db_path())
    try:
        assets = universe_symbols(config.universe_db_path())
        return run(db, assets, store, args.run_day, late_keys_path=keys)
    finally:
        db.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = project(args)
    except (BoundaryError, ProjectionError) as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    except StoreInterrupted as exc:
        print(exc.result.summary())
        print(
            f"store error, the run stopped partway: {exc}\n"
            "Only the graphs listed as written above were written.",
            file=sys.stderr,
        )
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:  # a missing database, or one without upstream's tables
        print(f"source error: {exc} (SQL_FINANCIAL_DB, SQL_UNIVERSE_DB)", file=sys.stderr)
        return 1
    print(result.summary())
    return 1 if result.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
