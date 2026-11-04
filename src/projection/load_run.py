"""Load one labelled backtest family in one command (Work item 29).

    uv run python cli/load_run.py --label rule --db rule_P1.db --db rule_P2.db --db rule_P3.db
    uv run python cli/load_run.py --label rule --dir /path/to/runs --write
    uv run python cli/load_run.py --label rule --dir /path/to/runs --write --to-production

The command is the orchestration the runbook used to spell out by hand: check the view contract
(optional), dry-run both projectors, optionally write the m018 and selection graphs, then verify
every graph with the read-only verifier. It reuses ``projection.backtest.run`` /
``run_selection``, the ingest gate they call, and ``projection.verify_backtest.verify``; there is
no second projector, gate or verifier here.

Each step stops at the first failure. A dry run (the default) contacts no store and prints the
graphs, rows, triples and unlinked counts each projector built. ``--write`` appends the m018 graphs
first and then their selection siblings; an existing graph is skipped, never appended to. When a
write has happened, every graph is verified and the final table records its stored triple count and
``PASS``/``FAIL`` checks. A verification failure never drops anything: the command prints the exact
one-graph ``DROP GRAPH <iri>`` commands for the graphs this run wrote, for the operator to run.

``--contract TARGET`` runs the same view-contract check as ``cli/check_view_contract.py`` first
(a ``portfolio-financial-analysis`` checkout path or its API URL). ``--dir DIR`` accepts every
``*_P<number>.db`` file in the directory, so the three final-run files need no repeated ``--db``.
Writing the production repository still needs ``--to-production``.

Exit status: 0 all requested steps passed; 1 a contract, source (including a missing database),
projection, store, gate or verification check failed; 2 a bad argument, a malformed label or two
inputs that would write the same graph.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from etl import config
from kg_store.graphdb import GraphDB, GraphDBError
from projection import project_backtest, project_selection
from projection.backtest import (
    RUN_LABEL_PATTERN,
    SELECTION_GRAPH_PREFIX,
    AssetInfo,
    GuardCatalog,
    ProjectionError,
    RunResult,
    SelectionRuleCatalog,
    StoreInterrupted,
    load_guard_catalog,
    load_selection_catalog,
    run,
    run_selection,
    universe_assets,
)
from projection.boundary import BoundaryError
from projection.contract_check import (
    ContractFetchError,
    check,
    check_service,
    fetch_contract,
)
from projection.expectations import ExpectationError, load_source
from projection.project_backtest import Database, open_store
from projection.source import FinancialSource
from projection.verify_backtest import Verification, VerificationError, verify

#: A final-run file name: a family, its window and the ``.db`` suffix (``rule_P1.db``).
_DB_FILE = re.compile(r"[a-z][a-z0-9_]*_P[0-9]+\.db")


class LoadError(ValueError):
    """A load step failed; the message names the step and the source."""


class InputError(ValueError):
    """The command's inputs cannot be loaded (a missing directory, repeated database, ...)."""


@dataclass
class TableRow:
    """One line of the final table: the graph, its stored triples and the verifier result."""

    graph: str
    triples: int | None
    passed: int | None = None
    total: int | None = None


def _label(text: str) -> str:
    if not re.fullmatch(RUN_LABEL_PATTERN, text):
        raise argparse.ArgumentTypeError(
            f"run label {text!r} does not match {RUN_LABEL_PATTERN} (as in rule)"
        )
    return text


def _database_path(text: str) -> Path:
    return Path(text).resolve()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--label",
        required=True,
        type=_label,
        metavar="LABEL",
        help="the run family's label ([a-z][a-z0-9_]{1,31}, as in rule)",
    )
    parser.add_argument(
        "--db",
        action="append",
        default=[],
        type=_database_path,
        metavar="PATH",
        help="a completed backtest database; repeat for each final-run file",
    )
    parser.add_argument(
        "--dir",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="a directory of *_P<number>.db files; every match is loaded",
    )
    parser.add_argument("--write", action="store_true", help="append the graphs to the store")
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    parser.add_argument(
        "--contract",
        metavar="TARGET",
        help="check the pinned view contract first: a portfolio-financial-analysis checkout or "
        "its API URL",
    )
    args = parser.parse_args(argv)
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    if not args.db and not args.dir:
        parser.error("at least one --db PATH or --dir DIR is required")
    return args


def _window_number(path: Path) -> int:
    match = re.search(r"_P([0-9]+)\.db$", path.name)
    assert match is not None, path.name
    return int(match.group(1))


def _directory_databases(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise InputError(f"--dir {directory}: not a directory")
    matches = sorted(
        (path for path in directory.iterdir() if path.is_file() and _DB_FILE.fullmatch(path.name)),
        key=lambda path: (_window_number(path), path.name),
    )
    if not matches:
        raise InputError(f"--dir {directory}: no *_P<number>.db file")
    return matches


def plan(args: argparse.Namespace) -> list[Database]:
    """Turn ``--db``/``--dir`` into one ordered, duplicate-free list of databases."""
    paths = list(args.db)
    for raw_directory in args.dir:
        paths.extend(_directory_databases(raw_directory.resolve()))
    resolved = [path.resolve() for path in paths]
    repeated = sorted({str(path) for path in resolved if resolved.count(path) > 1})
    if repeated:
        raise InputError("database given twice: " + ", ".join(repeated))
    return [Database(args.label, path) for path in resolved]


def _graph_names(database: Database) -> tuple[tuple[str, ...], tuple[str, ...]]:
    backtest = tuple(sorted(project_backtest.graph_names(database)))
    selection = tuple(sorted(project_selection.graph_names(database)))
    return backtest, selection


def _check_duplicate_graphs(databases: Sequence[Database]) -> None:
    seen: dict[str, Path] = {}
    for database in databases:
        backtest, selection = _graph_names(database)
        for graph in (*backtest, *selection):
            if graph in seen and seen[graph] != database.path:
                raise InputError(
                    f"{database.path} and {seen[graph]} would both write {graph}: "
                    "a graph belongs to one frozen run"
                )
            seen[graph] = database.path


def _view_contract(target: str) -> None:
    """Run the pinned-contract check from ``cli/check_view_contract.py`` without its CLI."""
    if target.startswith(("http://", "https://")):
        declared = fetch_contract(target)
        print(
            f"service: contract_version {declared.contract_version}, code {declared.code_version}"
        )
        if declared.database is not None:
            print(f"service database: schema_version {declared.database.schema_version}")
        report = check_service(declared, load_source())
    else:
        report = check(Path(target))
    for line in report.notes:
        print(f"NOTE  {line}")
    for line in report.drift:
        print(f"DRIFT {line}")
    if report.drift:
        raise LoadError(f"view contract: {len(report.drift)} drift(s); do not project")
    print("view contract: OK")


def _failed(result: RunResult) -> str | None:
    if result.report.stopped:
        return "boundary stopped: " + "; ".join(result.report.stop_reasons or ["no reason given"])
    if result.rejected:
        return "gate refused " + ", ".join(
            f"{graph}: {why}" for graph, why in sorted(result.rejected.items())
        )
    if not result.graphs:
        return "the source projected no graph"
    return None


def _dry_run(
    database: Database,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
) -> tuple[RunResult, RunResult]:
    source = FinancialSource.open(database.path)
    try:
        backtest = run(source, assets, guard_catalog, database.label)
        selection = run_selection(source, assets, selection_catalog, database.label)
    finally:
        source.close()
    print(f"\ndry run m018: {database.path}")
    print(backtest.summary())
    problem = _failed(backtest)
    if problem is not None:
        raise LoadError(f"m018 dry run, {database.path}: {problem}")
    print(f"\ndry run selection: {database.path}")
    print(selection.summary())
    problem = _failed(selection)
    if problem is not None:
        raise LoadError(f"selection dry run, {database.path}: {problem}")
    return backtest, selection


def _write_m018(
    database: Database,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    store: GraphDB,
) -> RunResult:
    source = FinancialSource.open(database.path)
    try:
        result = run(source, assets, guard_catalog, database.label, store)
    finally:
        source.close()
    print(f"\nwrite m018: {database.path}")
    print(result.summary())
    problem = _failed(result)
    if problem is not None:
        raise LoadError(f"m018 write, {database.path}: {problem}")
    return result


def _write_selection(
    database: Database,
    assets: Mapping[str, AssetInfo],
    selection_catalog: SelectionRuleCatalog,
    store: GraphDB,
) -> RunResult:
    source = FinancialSource.open(database.path)
    try:
        result = run_selection(source, assets, selection_catalog, database.label, store)
    finally:
        source.close()
    print(f"\nwrite selection: {database.path}")
    print(result.summary())
    problem = _failed(result)
    if problem is not None:
        raise LoadError(f"selection write, {database.path}: {problem}")
    return result


def _verify_graph(
    graph: str,
    database: Database,
    store: GraphDB,
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
) -> Verification:
    if graph.startswith(SELECTION_GRAPH_PREFIX):
        return verify(
            store,
            graph,
            database.path,
            database.label,
            selection_catalog=selection_catalog,
            repository=store.repository,
            host=store.host,
        )
    return verify(
        store,
        graph,
        database.path,
        database.label,
        catalog=guard_catalog,
        repository=store.repository,
        host=store.host,
    )


def _print_table(rows: Sequence[TableRow]) -> None:
    print("\ngraph                                                              triples  checks")
    for row in rows:
        triples = "-" if row.triples is None else f"{row.triples:,}"
        checks = "not verified (dry run)" if row.total is None else f"{row.passed}/{row.total}"
        print(f"{row.graph:<66} {triples:>10}  {checks}")


def _print_drops(written: Sequence[str]) -> None:
    graphs = sorted(set(written))
    if not graphs:
        return
    print(
        "\nRollback: this run wrote the graph(s) below. Drop one at a time, only after deciding "
        "the loss is acceptable:\n" + "\n".join(f"DROP GRAPH <{graph}>" for graph in graphs),
        file=sys.stderr,
    )


def _prepare(
    args: argparse.Namespace,
) -> tuple[
    list[Database],
    Mapping[str, AssetInfo],
    GuardCatalog,
    SelectionRuleCatalog,
    dict[Path, tuple[RunResult, RunResult]],
]:
    """Plan, check the optional contract, load the catalogs and dry-run every database."""
    databases = plan(args)
    _check_duplicate_graphs(databases)
    if args.contract:
        _view_contract(args.contract)
    assets = universe_assets(config.universe_db_path())
    guard_catalog = load_guard_catalog(config.schema_dir() / "rules.ttl")
    selection_catalog = load_selection_catalog(config.schema_dir() / "rules.ttl")
    dry: dict[Path, tuple[RunResult, RunResult]] = {}
    for database in databases:
        dry[database.path] = _dry_run(database, assets, guard_catalog, selection_catalog)
    return databases, assets, guard_catalog, selection_catalog, dry


def _write_all(  # noqa: PLR0913, PLR0917 -- the stage's inputs are explicit
    databases: Sequence[Database],
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
    store: GraphDB,
    written: list[str],
) -> None:
    """Write every m018 graph first, then every selection sibling."""
    for database in databases:
        result = _write_m018(database, assets, guard_catalog, store)
        written.extend(result.written)
    for database in databases:
        result = _write_selection(database, assets, selection_catalog, store)
        written.extend(result.written)


def _verify_all(
    databases: Sequence[Database],
    dry: Mapping[Path, tuple[RunResult, RunResult]],
    store: GraphDB,
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
) -> tuple[list[TableRow], bool]:
    """Verify every graph in turn and stop at the first failed check."""
    rows: list[TableRow] = []
    for database in databases:
        backtest, selection = dry[database.path]
        for graph in (*sorted(backtest.graphs), *sorted(selection.graphs)):
            verification = _verify_graph(graph, database, store, guard_catalog, selection_catalog)
            print(verification.summary())
            rows.append(
                TableRow(
                    graph,
                    verification.triples,
                    sum(check.passed for check in verification.checks),
                    len(verification.checks),
                )
            )
            if not verification.ok:
                return rows, True
    return rows, False


def _report_failure(exc: BaseException, written: Sequence[str]) -> int:
    if isinstance(exc, InputError):
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if isinstance(exc, (ContractFetchError, ExpectationError)):
        print(f"contract error: {exc}", file=sys.stderr)
    elif isinstance(exc, sqlite3.Error):
        print(f"source error: {exc}", file=sys.stderr)
    elif isinstance(exc, GraphDBError):
        print(f"store error: {exc}", file=sys.stderr)
    elif isinstance(exc, OSError):
        print(f"file error: {exc}", file=sys.stderr)
    else:
        print(f"STOPPED\n{exc}", file=sys.stderr)
    _print_drops(written)
    return 1


_FAILURES = (
    InputError,
    LoadError,
    BoundaryError,
    ProjectionError,
    VerificationError,
    ContractFetchError,
    ExpectationError,
    sqlite3.Error,
    GraphDBError,
    OSError,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    written: list[str] = []
    try:
        databases, assets, guard_catalog, selection_catalog, dry = _prepare(args)
        if not args.write:
            _print_table(
                [
                    TableRow(graph, result.graphs[graph])
                    for _, (backtest, selection) in dry.items()
                    for result in (backtest, selection)
                    for graph in sorted(result.graphs)
                ]
            )
            return 0
        store = open_store(args)
        assert store is not None  # open_store only returns None without --write
        _write_all(databases, assets, guard_catalog, selection_catalog, store, written)
        rows, failed = _verify_all(databases, dry, store, guard_catalog, selection_catalog)
    except StoreInterrupted as exc:
        written.extend(exc.result.written)
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
        _print_drops(written)
        return 1
    except _FAILURES as exc:
        return _report_failure(exc, written)
    _print_table(rows)
    if failed:
        _print_drops(written)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
