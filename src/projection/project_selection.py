"""Project the six backtest selection views into one sibling graph per run (Work item 26).

The command-line policy of the selection-side projection: which databases are read, their run
labels, the production guard, and the exit status. ``cli/project_selection.py`` is its thin entry
point (constitution Project structure #10); :mod:`projection.backtest` does the work.

    uv run python cli/project_selection.py --db rule=rule_P1.db [--db rule=rule_P2.db ...]
    uv run python cli/project_selection.py --db rule=rule_P1.db --check-store
    uv run python cli/project_selection.py --db rule=rule_P1.db --write

``--db`` takes ``LABEL=PATH`` exactly like ``cli/project_backtest.py``. The selection side lives in
``urn:graph:derived:backtest:selection:{label}:{window}:{run_id}``, a sibling of the m018 graph, so
an already-written m018 graph is neither a target nor rewritten.

A dry run (the default) reads every database, runs the boundary, builds each run's batch and
validates it against ``shapes.ttl`` beside ``rules.ttl`` and the universe assets; it never contacts
the store and writes nothing. ``--check-store`` builds the same graphs and runs the full gate plan
against the live store with ``SELECT`` only, reporting each graph as would-be-written,
already-in-the-store (skipped) or refused; it never writes. ``--write`` appends each graph through the ingest gate, but a backtest
is a frozen artifact and where it lives is the maintainer's decision: writing to the production
repository (``KG_REPOSITORY=portfolio``) also needs ``--to-production``, and without it the run
exits 2 before any graph is built or written. A graph that already exists is never appended to; it
is reported and skipped.

Exit status: 0 on success; 1 if a boundary, projection, store or gate check stops the run; 2 on a
bad argument, a missing or malformed run label, a database repeated on the command line, or two
databases that would produce the same graph name.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from typing import Any

from etl import config
from kg_store.graphdb import GraphDB, GraphDBError
from projection.backtest import (
    ProjectionError,
    RunResult,
    StoreInterrupted,
    load_selection_catalog,
    project_selection_source,
    read_view,
    run_selection,
    selection_graph_name,
    universe_assets,
)
from projection.boundary import BoundaryError
from projection.project_backtest import Database, database_argument, open_store
from projection.source import FinancialSource
from projection.store_check import check_graphs


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--db",
        action="append",
        required=True,
        type=database_argument,
        metavar="LABEL=PATH",
        help="a completed backtest database and the label naming its run family; repeat to "
        "project several in one run",
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
    return args


def graph_names(database: Database) -> set[str]:
    """The selection graph names a database's ``v_book`` rows would produce."""
    source = FinancialSource.open(database.path)
    try:
        books = read_view(source, "v_book")
    finally:
        source.close()
    names: set[str] = set()
    for row in books:
        try:
            run_id = int(row["backtest_run_id"])
        except (TypeError, ValueError):
            raise ProjectionError(
                f"v_book: backtest_run_id {row.get('backtest_run_id')!r} is not an integer"
            ) from None
        names.add(selection_graph_name(database.label, str(row["window_id"]), run_id))
    return names


def check_store(args: argparse.Namespace) -> bool:
    """Build each graph and validate it beside the live store's context; write nothing."""
    store = GraphDB.from_env()
    assets = universe_assets(config.universe_db_path())
    catalog = load_selection_catalog(config.schema_dir() / "rules.ttl")
    failed = False
    for database in args.db:
        source = FinancialSource.open(database.path)
        try:
            projection = project_selection_source(source, assets, catalog, database.label)
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


def project(args: argparse.Namespace) -> list[tuple[Database, RunResult]]:
    """Check every database's graph name, then read, validate and (when asked) write each."""
    seen: dict[str, Database] = {}
    for database in args.db:
        for name in sorted(graph_names(database)):
            if name in seen:
                print(
                    f"{database.path} and {seen[name].path} would both write {name}: a graph "
                    "belongs to one frozen run",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            seen[name] = database
    store = open_store(args)
    assets = universe_assets(config.universe_db_path())
    catalog = load_selection_catalog(config.schema_dir() / "rules.ttl")
    results: list[tuple[Database, RunResult]] = []
    for database in args.db:
        source = FinancialSource.open(database.path)
        try:
            results.append(
                (
                    database,
                    run_selection(source, assets, catalog, database.label, store),
                )
            )
        finally:
            source.close()
    return results


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911 -- one per failure kind
    args = parse_args(argv)
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
    except sqlite3.Error as exc:  # a missing database, or one without the selection views
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
        print(result.summary())
        failed = failed or bool(result.rejected) or result.report.stopped
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
