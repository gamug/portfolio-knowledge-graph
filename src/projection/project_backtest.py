"""Project the eight m018 backtest/GUARD views into one graph per run (T-207).

The command-line policy of the backtest projection: which databases are read, the production
guard, and the exit status. ``cli/project_backtest.py`` is its thin entry point (constitution
Project structure #10); :mod:`projection.backtest` does the work.

    uv run python cli/project_backtest.py --db rule_P1.db [--db rule_P2.db ...]
    uv run python cli/project_backtest.py --db rule_P1.db --write

A dry run (the default) reads every database, runs the boundary, builds each run's batch and
validates it against ``shapes.ttl``; it never contacts the store and writes nothing. ``--write``
appends each graph through the ingest gate, but a backtest is a frozen artifact and where it lives
is the maintainer's decision: writing to the production repository (``KG_REPOSITORY=portfolio``)
also needs ``--to-production``, and without it the run exits 2 before reading anything. A graph
that already exists is never appended to; it is reported and skipped.

Exit status: 0 on success; 1 if a boundary, projection, store or gate check stops the run; 2 on a
bad argument, a database repeated on the command line, or two databases that would produce the
same graph name.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from etl import config
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError
from projection.backtest import (
    ProjectionError,
    RunResult,
    StoreInterrupted,
    graph_name,
    load_guard_catalog,
    read_view,
    run,
    universe_assets,
)
from projection.boundary import BoundaryError
from projection.source import FinancialSource


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--db",
        action="append",
        required=True,
        type=Path,
        metavar="PATH",
        help="a completed backtest database; repeat to project several in one run",
    )
    parser.add_argument("--write", action="store_true", help="append the graphs to the store")
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    args = parser.parse_args(argv)
    args.db = [path.resolve() for path in args.db]
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    repeated = sorted({str(path) for path in args.db if args.db.count(path) > 1})
    if repeated:
        parser.error("--db given twice: " + ", ".join(repeated))
    return args


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """The store a ``--write`` appends to; production needs the explicit opt-in."""
    if not args.write:
        return None
    store = GraphDB.from_env()
    if store.repository == PRODUCTION_REPOSITORY and not args.to_production:
        print(
            "--write to the production repository needs --to-production: a backtest is a frozen "
            "artifact and where it lives is the maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return store


def graph_names(path: Path) -> set[str]:
    """The graph names a database's ``v_book`` rows would produce (read before any write)."""
    source = FinancialSource.open(path)
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
        names.add(graph_name(str(row["window_id"]), run_id))
    return names


def project(args: argparse.Namespace) -> list[tuple[Path, RunResult]]:
    """Check every database's graph name, then read, validate and (when asked) write each."""
    seen: dict[str, Path] = {}
    for path in args.db:
        for name in sorted(graph_names(path)):
            if name in seen:
                print(
                    f"{path} and {seen[name]} would both write {name}: a graph belongs to one "
                    "frozen run",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            seen[name] = path
    store = open_store(args)
    assets = universe_assets(config.universe_db_path())
    catalog = load_guard_catalog(config.schema_dir() / "rules.ttl")
    results: list[tuple[Path, RunResult]] = []
    for path in args.db:
        source = FinancialSource.open(path)
        try:
            results.append((path, run(source, assets, catalog, store)))
        finally:
            source.close()
    return results


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
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
    except sqlite3.Error as exc:  # a missing database, or one without the m018 views
        print(f"source error: {exc} (--db)", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1
    failed = False
    for path, result in results:
        print(f"\n{path}")
        print(result.summary())
        failed = failed or bool(result.rejected) or result.report.stopped
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
