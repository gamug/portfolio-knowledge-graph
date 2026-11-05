"""Load one labelled backtest family in one command (Work item 29, pre-flight in Work item 31).

    uv run python cli/load_run.py --label rule --db rule_P1.db --db rule_P2.db --db rule_P3.db
    uv run python cli/load_run.py --label rule --dir /path/to/runs --check-store
    uv run python cli/load_run.py --label rule --dir /path/to/runs --write
    uv run python cli/load_run.py --label rule --dir /path/to/runs --write --to-production

The command is the orchestration the runbook used to spell out by hand: check the view contract
(optional), dry-run both projectors, pre-flight every graph through the ingest gate, optionally
write the m018 and selection graphs, then verify every graph with the read-only verifier. It
reuses ``projection.backtest.run`` / ``run_selection``, the gate they call, and
``projection.verify_backtest.verify``; there is no second projector, gate or verifier here.

A dry run (the default) contacts no store and prints the graphs, rows, triples and unlinked counts
each projector built. ``--check-store`` runs only the read-only pre-flight: it builds every graph,
calls the same ``gate.plan`` a write uses for every one of them with the store's real context
(``SELECT`` only), and reports each graph as would-be-written, already-in-the-store (skipped) or
refused. It writes nothing and refuses ``--write`` and ``--to-production``.

With ``--write`` the pre-flight runs before anything is written. If any graph is refused, the
command stops with nothing written and lists every refusal with its graph name and the gate's
message. A graph already in the store is reported and skipped. Only after every graph is accepted
does it apply the plans the pre-flight already computed with ``gate.write`` (it never plans twice),
then verify every graph as before. A write failure after the pre-flight names the graphs written,
the graph in doubt (if any) and prints the exact one-graph ``DROP GRAPH <iri>`` commands for the
graphs this run wrote; it never drops anything itself.

``--contract TARGET`` runs the same view-contract check as ``cli/check_view_contract.py`` first
(a ``portfolio-financial-analysis`` checkout path or its API URL). ``--dir DIR`` accepts every
``*_{P<number>|H<number>}.db`` file in the directory, so the final-run files need no repeated ``--db``.
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
from dataclasses import dataclass, field
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
    RunPlan,
    RunResult,
    SelectionRuleCatalog,
    StoreInterrupted,
    load_guard_catalog,
    load_selection_catalog,
    plan_run,
    plan_selection,
    run,
    run_selection,
    universe_assets,
    write_run,
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
_DB_FILE = re.compile(r"[a-z][a-z0-9_]*_[PH][0-9]+\.db")

#: The statuses a graph can carry in the pre-flight and the final table.
WOULD_WRITE = "would-be-written"
ALREADY_IN_STORE = "already-in-the-store"
REFUSED = "refused"
WRITTEN = "written"
IN_DOUBT = "in doubt"
DRY_RUN = "not checked (dry run)"


class LoadError(ValueError):
    """A load step failed; the message names the step and the source."""


class InputError(ValueError):
    """The command's inputs cannot be loaded (a missing directory, repeated database, ...)."""


@dataclass
class TableRow:
    """One line of the final table: the graph, its stored triples, status and verifier result."""

    graph: str
    triples: int | None
    status: str
    passed: int | None = None
    total: int | None = None


@dataclass
class Preflight:
    """Every planned run and the status each graph got from the real gate.

    Each ``RunPlan`` holds only its would-be-written graphs. No graph is written until every
    database's m018 and selection graphs have been planned, so a refusal in a later graph cannot
    leave an earlier one in the store.
    """

    runs: list[tuple[Database, RunPlan, RunPlan]] = field(default_factory=list)
    statuses: dict[str, str] = field(default_factory=dict)
    refusals: dict[str, str] = field(default_factory=dict)


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
        help="a directory of *_{P<number>|H<number>}.db files; every match is loaded",
    )
    parser.add_argument("--write", action="store_true", help="append the graphs to the store")
    parser.add_argument(
        "--check-store",
        action="store_true",
        help="run the read-only pre-flight against the live store; write nothing",
    )
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
    if args.check_store and args.write:
        parser.error("--check-store only reads; do not combine it with --write")
    if args.check_store and args.to_production:
        parser.error("--check-store never writes; drop --to-production")
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
        raise InputError(f"--dir {directory}: no *_P<number>.db or *_H<number>.db file")
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


def _projection_problem(result: RunResult) -> str | None:
    """A problem before any gate status exists (a boundary stop or an empty projection)."""
    if result.report.stopped:
        return "boundary stopped: " + "; ".join(result.report.stop_reasons or ["no reason given"])
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


def _graph_status(planned: RunPlan) -> dict[str, str]:
    """The status of every graph in one planned run, from the gate's own outcome."""
    statuses: dict[str, str] = {}
    for graph in sorted(planned.result.graphs):
        if graph in planned.result.rejected:
            statuses[graph] = REFUSED
        elif graph in planned.result.already_in_store:
            statuses[graph] = ALREADY_IN_STORE
        else:
            statuses[graph] = WOULD_WRITE
    return statuses


def _preflight(
    databases: Sequence[Database],
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
    store: GraphDB,
) -> Preflight:
    """Plan every m018 and selection graph against the store before writing any of them."""
    print(
        "\npre-flight: gate.plan for every graph with the store's context (SELECT only); "
        "nothing is written"
    )
    preflight = Preflight()
    for database in databases:
        source = FinancialSource.open(database.path)
        try:
            backtest = plan_run(source, assets, guard_catalog, database.label, store)
            selection = plan_selection(source, assets, selection_catalog, database.label, store)
        finally:
            source.close()
        for kind, planned in (("m018", backtest), ("selection", selection)):
            print(f"\npre-flight {kind}: {database.path}")
            print(planned.result.summary())
            problem = _projection_problem(planned.result)
            if problem is not None:
                raise LoadError(f"{kind} pre-flight, {database.path}: {problem}")
            for graph, status in _graph_status(planned).items():
                preflight.statuses[graph] = status
                print(f"  pre-flight {status}: {graph}")
                if status == REFUSED:
                    why = planned.result.rejected[graph]
                    preflight.refusals[graph] = why
                    print(f"    {why}")
        preflight.runs.append((database, backtest, selection))
    return preflight


def _preflight_rows(preflight: Preflight) -> list[TableRow]:
    rows: list[TableRow] = []
    for _, backtest, selection in preflight.runs:
        for planned in (backtest, selection):
            for graph in sorted(planned.result.graphs):
                rows.append(
                    TableRow(
                        graph,
                        planned.result.graphs[graph],
                        preflight.statuses.get(graph, WOULD_WRITE),
                    )
                )
    return rows


def _report_preflight_refusals(preflight: Preflight) -> None:
    print(
        f"\npre-flight refused {len(preflight.refusals)} graph(s); nothing was written: "
        + ", ".join(sorted(preflight.refusals)),
        file=sys.stderr,
    )


def _write_all(preflight: Preflight, store: GraphDB, written: list[str]) -> None:
    """Apply the already-computed plans: every m018 graph first, then every selection sibling."""
    for kind, position in (("m018", 0), ("selection", 1)):
        for database, backtest, selection in preflight.runs:
            planned = (backtest, selection)[position]
            print(f"\nwrite {kind}: {database.path}")
            write_run(planned, store)
            print(planned.result.summary())
            written.extend(planned.result.written)
            for graph in planned.result.written:
                preflight.statuses[graph] = WRITTEN
            problem = _failed(planned.result)
            if problem is not None:
                raise LoadError(f"{kind} write, {database.path}: {problem}")


def _verify_graph(  # noqa: PLR0913, PLR0917 -- the verifier's inputs are explicit
    graph: str,
    database: Database,
    store: GraphDB,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
) -> Verification:
    if graph.startswith(SELECTION_GRAPH_PREFIX):
        return verify(
            store,
            graph,
            database.path,
            database.label,
            assets=assets,
            selection_catalog=selection_catalog,
            repository=store.repository,
            host=store.host,
        )
    return verify(
        store,
        graph,
        database.path,
        database.label,
        assets=assets,
        catalog=guard_catalog,
        repository=store.repository,
        host=store.host,
    )


def _print_table(rows: Sequence[TableRow], *, note: str = "not verified (dry run)") -> None:
    print(
        "\ngraph                                                              triples  "
        "status                  checks"
    )
    for row in rows:
        triples = "-" if row.triples is None else f"{row.triples:,}"
        checks = note if row.total is None else f"{row.passed}/{row.total}"
        print(f"{row.graph:<66} {triples:>10}  {row.status:<22}  {checks}")


def _print_drops(written: Sequence[str]) -> None:
    graphs = sorted(set(written))
    if not graphs:
        return
    print(
        "\nRollback: this run wrote the graph(s) below. Drop one at a time, only after deciding "
        "the loss is acceptable:\n" + "\n".join(f"DROP GRAPH <{graph}>" for graph in graphs),
        file=sys.stderr,
    )


def _inputs(
    args: argparse.Namespace,
) -> tuple[
    list[Database],
    Mapping[str, AssetInfo],
    GuardCatalog,
    SelectionRuleCatalog,
]:
    """Plan the inputs, check the optional contract and load the catalogs; no database is read."""
    databases = plan(args)
    _check_duplicate_graphs(databases)
    if args.contract:
        _view_contract(args.contract)
    assets = universe_assets(config.universe_db_path())
    guard_catalog = load_guard_catalog(config.schema_dir() / "rules.ttl")
    selection_catalog = load_selection_catalog(config.schema_dir() / "rules.ttl")
    return databases, assets, guard_catalog, selection_catalog


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
    databases, assets, guard_catalog, selection_catalog = _inputs(args)
    dry: dict[Path, tuple[RunResult, RunResult]] = {}
    for database in databases:
        dry[database.path] = _dry_run(database, assets, guard_catalog, selection_catalog)
    return databases, assets, guard_catalog, selection_catalog, dry


def _open_check_store() -> GraphDB:
    """The read-only pre-flight's store; production is readable without the write opt-in."""
    return GraphDB.from_env()


def _verify_all(
    preflight: Preflight,
    store: GraphDB,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
) -> tuple[list[TableRow], bool]:
    """Verify every graph in turn and stop at the first failed check."""
    rows: list[TableRow] = []
    for database, backtest, selection in preflight.runs:
        for planned in (backtest, selection):
            for graph in sorted(planned.result.graphs):
                verification = _verify_graph(
                    graph, database, store, assets, guard_catalog, selection_catalog
                )
                print(verification.summary())
                rows.append(
                    TableRow(
                        graph,
                        verification.triples,
                        preflight.statuses.get(graph, WRITTEN),
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


def _report_interrupted(
    exc: StoreInterrupted, preflight: Preflight, written: Sequence[str]
) -> None:
    """Name what was written, what is in doubt and the one-graph drops; never drop anything."""
    written = sorted(set(written))
    print(exc.result.summary())
    for graph in written:
        preflight.statuses[graph] = WRITTEN
    if exc.result.in_doubt:
        preflight.statuses[exc.result.in_doubt] = IN_DOUBT
    print(
        f"\nstore error after the pre-flight: {exc}\n"
        + ("Graphs written: " + ", ".join(written) + "." if written else "No graph was written.")
        + (
            f"\nIn doubt: {exc.result.in_doubt} was sent but the store's answer was lost; it may "
            "have been written."
            if exc.result.in_doubt
            else "\nNo graph is in doubt: the store answered with an error before the graph was "
            "written."
        ),
        file=sys.stderr,
    )
    _print_drops(written)
    _print_table(_preflight_rows(preflight), note="not verified (write stopped)")


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


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911 -- one per failure kind
    args = parse_args(argv)
    written: list[str] = []
    preflight: Preflight | None = None
    try:
        if args.check_store:
            databases, assets, guard_catalog, selection_catalog = _inputs(args)
            preflight = _preflight(
                databases,
                assets,
                guard_catalog,
                selection_catalog,
                _open_check_store(),
            )
            _print_table(_preflight_rows(preflight), note="not verified (pre-flight)")
            if preflight.refusals:
                _report_preflight_refusals(preflight)
                return 1
            print(
                "\npre-flight passed; nothing was written (--check-store)",
                file=sys.stderr,
            )
            return 0
        databases, assets, guard_catalog, selection_catalog, dry = _prepare(args)
        if not args.write:
            _print_table(
                [
                    TableRow(graph, result.graphs[graph], DRY_RUN)
                    for _, (backtest, selection) in dry.items()
                    for result in (backtest, selection)
                    for graph in sorted(result.graphs)
                ]
            )
            return 0
        store = open_store(args)
        assert store is not None  # open_store only returns None without --write
        preflight = _preflight(databases, assets, guard_catalog, selection_catalog, store)
        if preflight.refusals:
            _print_table(_preflight_rows(preflight), note="not verified (pre-flight)")
            _report_preflight_refusals(preflight)
            return 1
        _write_all(preflight, store, written)
        rows, failed = _verify_all(preflight, store, assets, guard_catalog, selection_catalog)
    except StoreInterrupted as exc:
        written.extend(exc.result.written)
        assert preflight is not None  # a write only happens after the pre-flight
        _report_interrupted(exc, preflight, written)
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
