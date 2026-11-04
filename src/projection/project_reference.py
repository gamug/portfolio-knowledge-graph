"""Project the ticker-history and orchestrator views: CLI policy (T-354).

The command-line policy of the reference/process projection: which database is read, its label,
the snapshot date, the production guard and the exit status. ``cli/project_reference.py`` is its
thin entry point (constitution Project structure #10); :mod:`projection.reference` does the work.

    uv run python cli/project_reference.py --db live=base.db --as-of 2026-11-04
    uv run python cli/project_reference.py --db live=base.db --as-of 2026-11-04 --check-store
    uv run python cli/project_reference.py --db live=base.db --write

``--db`` takes ``LABEL=PATH``. The label names the source family and is part of the ticker-history
graph and every individual IRI, so two databases never collide. A dry run (the default) reads the
database, runs the boundary, builds every graph and validates it against ``shapes.ttl``; it never
contacts the store and writes nothing. ``--check-store`` builds the same graphs and runs the full
gate plan against the live store with ``SELECT`` only, reporting each graph as would-be-written,
already-in-the-store (skipped) or refused; it never writes. ``--write`` appends each graph through the ingest gate, but
writing to the production repository (``KG_REPOSITORY=portfolio``) also needs
``--to-production``; without it the run exits 2 before any graph is built or written. A graph that
already exists is never appended to; it is reported and skipped.

With 0 rows in both orchestrator views the run builds no orchestrator graph and prints that there
is nothing to write; with 0 ticker-history rows the same is printed for that view.

Exit status: 0 on success; 1 if a boundary, projection, store or gate check stops the run; 2 on a
bad argument, a missing or malformed label, a malformed date, a database repeated on the command
line, or two databases sharing a label.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from etl import config
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError
from projection.backtest import RUN_LABEL_PATTERN, ProjectionError, universe_assets
from projection.boundary import BoundaryError
from projection.reference import ReferenceRunResult, StoreInterrupted, project_source, run
from projection.source import FinancialSource
from projection.store_check import check_graphs


@dataclass(frozen=True)
class Database:
    """One ``--db LABEL=PATH``: the source family's label and the database it is read from."""

    label: str
    path: Path


def _database(text: str) -> Database:
    """``LABEL=PATH`` -> :class:`Database`; a missing or malformed label is an argument error."""
    label, separator, raw_path = text.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(f"expected LABEL=PATH, got {text!r}")
    if not re.fullmatch(RUN_LABEL_PATTERN, label):
        raise argparse.ArgumentTypeError(
            f"run label {label!r} does not match {RUN_LABEL_PATTERN} (as in live=base.db)"
        )
    if not raw_path:
        raise argparse.ArgumentTypeError(f"{label}: no database path after '='")
    return Database(label, Path(raw_path).resolve())


def _snapshot(text: str) -> str:
    """``--as-of``: a ``YYYY-MM-DD`` date, refused here rather than at projection time."""
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a YYYY-MM-DD date") from None


def today() -> str:
    """Today in UTC: the default ``--as-of``."""
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--db",
        action="append",
        required=True,
        type=_database,
        metavar="LABEL=PATH",
        help="a v18 database and the label naming its source family; repeat for several",
    )
    parser.add_argument(
        "--as-of",
        type=_snapshot,
        default=None,
        metavar="YYYY-MM-DD",
        help="the ticker-history snapshot date; names the graph (default: today in UTC)",
    )
    parser.add_argument("--write", action="store_true", help="append the graphs to the store")
    parser.add_argument(
        "--check-store",
        action="store_true",
        help="read the live store, validate the same batches beside its context, write nothing",
    )
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    args = parser.parse_args(argv)
    if args.check_store and args.write:
        parser.error("--check-store only reads; do not combine it with --write")
    if args.check_store and args.to_production:
        parser.error("--check-store never writes; drop --to-production")
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    paths = [database.path for database in args.db]
    repeated = sorted({str(path) for path in paths if paths.count(path) > 1})
    if repeated:
        parser.error("--db given twice: " + ", ".join(repeated))
    labels = [database.label for database in args.db]
    repeated_labels = sorted({label for label in labels if labels.count(label) > 1})
    if repeated_labels:
        parser.error("--db label given twice: " + ", ".join(repeated_labels))
    return args


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """The store a ``--write`` appends to; production needs the explicit opt-in."""
    if not args.write:
        return None
    store = GraphDB.from_env()
    if store.repository == PRODUCTION_REPOSITORY and not args.to_production:
        print(
            "--write to the production repository needs --to-production: a ticker-history "
            "snapshot is reference data and where it lives is the maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


def check_store(args: argparse.Namespace) -> bool:
    """Build each graph and validate it beside the live store's context; write nothing."""
    snapshot = args.as_of or today()
    store = GraphDB.from_env()
    assets = universe_assets(config.universe_db_path())
    failed = False
    for database in args.db:
        source = FinancialSource.open(database.path)
        try:
            projection = project_source(source, assets, database.label, snapshot)
        finally:
            source.close()
        graphs = {
            graph: projection.projection.turtle(graph) for graph in projection.projection.graphs
        }
        failed = (
            check_graphs(
                store,
                graphs,
                config.schema_dir(),
                label=f"{database.label}: {database.path}",
            )
            or failed
        )
    return failed


def project(args: argparse.Namespace) -> list[tuple[Database, ReferenceRunResult]]:
    """Read, validate and (when asked) write every database's graphs."""
    snapshot = args.as_of or today()
    store = open_store(args)
    assets = universe_assets(config.universe_db_path())
    results: list[tuple[Database, ReferenceRunResult]] = []
    for database in args.db:
        source = FinancialSource.open(database.path)
        try:
            results.append((database, run(source, assets, database.label, snapshot, store)))
        finally:
            source.close()
    return results


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911 -- one per failure kind
    args = parse_args(argv)
    args.as_of = args.as_of or today()
    check_failed = False
    results: list[tuple[Database, Any]] = []
    try:
        if args.check_store:
            check_failed = check_store(args)
        else:
            results = project(args)
    except (BoundaryError, ProjectionError) as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    except StoreInterrupted as exc:
        print(exc.result.summary())
        print(
            f"store error, the run stopped partway: {exc}\n"
            + (
                "The graphs listed as written above were written; the one in doubt may be too."
                if exc.result.in_doubt
                else "Only the graphs listed as written above were written."
            ),
            file=sys.stderr,
        )
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:  # a missing database, or one without the three views
        print(f"source error: {exc} (--db LABEL=PATH)", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1
    if args.check_store:
        return 1 if check_failed else 0
    failed = False
    for database, result in results:
        print(f"\n{database.label}: {database.path}")
        print(f"snapshot: {args.as_of}")
        print(result.summary())
        failed = failed or bool(result.rejected) or result.report.stopped
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
