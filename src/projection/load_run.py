"""Load one labelled backtest family in one command (Work items 29, 31 and 35).

    uv run python cli/load_run.py --label final --dir /path/to/delivery --check-store
    uv run python cli/load_run.py --label final --dir /path/to/delivery --write
    uv run python cli/load_run.py --label rule --dir /path/to/pilot --no-manifest --no-config

The command is the orchestration the runbook used to spell out by hand: check the view contract
(optional), dry-run both projectors, pre-flight every graph through the ingest gate, optionally
write the m018, selection and metadata graphs, then verify every graph. It reuses
``projection.backtest.run`` / ``run_selection``, the gate they call, and
``projection.verify_backtest.verify``; there is no second projector, gate or verifier here. The
delivery files (``SHA256SUMS`` and ``config_<label>.md``) are read by ``projection.delivery`` and
the run metadata is built and verified by ``projection.run_metadata``.

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
(a ``portfolio-financial-analysis`` checkout path or its API URL). ``--dir DIR`` is the delivery
folder: it discovers ``<label>_<window>.db`` files for the six allowed windows, verifies the
``SHA256SUMS`` manifest before any database is opened, reads ``config_<label>.md`` and writes the
metadata graph. ``--windows P1,H1`` requires those windows to be present. ``--no-manifest`` and
``--no-config`` go together as the pilot's explicit legacy mode; they are refused when either
delivery file is present. Writing the production repository still needs ``--to-production``, and
production receives only the ``final`` label.

Exit status: 0 all requested steps passed; 1 a contract, source (including a missing database),
projection, store, gate or verification check failed; 2 a bad argument, a malformed label, a
delivery file that cannot be verified, or two inputs that would write the same graph.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from etl import config
from kg_store import gate
from kg_store.graphdb import GraphDB, GraphDBError, announce_target
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
from projection.delivery import (
    Delivery,
    DeliveryError,
    WindowSource,
    load_delivery,
    parse_windows,
)
from projection.disk_space import DiskMonitor, DiskSpaceError
from projection.expectations import ExpectationError, load_source
from projection.project_backtest import Database, open_store
from projection.run_metadata import (
    MetadataError,
    MetadataProjection,
    MetaPlan,
    plan_meta,
    validate_metadata,
    verify_metadata,
    write_metadata,
)
from projection.source import FinancialSource
from projection.verify_backtest import Verification, VerificationError, verify

#: The statuses a graph can carry in the pre-flight and the final table.
WOULD_WRITE = "would-be-written"
ALREADY_IN_STORE = "already-in-the-store"
REFUSED = "refused"
WRITTEN = "written"
IN_DOUBT = "in doubt"
DRY_RUN = "not checked (dry run)"

#: A window slower than this is flagged for the upstream reviewer.
SLOW_WINDOW_SECONDS = 30 * 60

#: GraphDB's HTTP 500 when its data volume is below the hard floor.
_LOW_DISK = "critically low disk space"
_PERCENT = 100


class LoadError(ValueError):
    """A load step failed; the message names the step and the source."""


class InputError(ValueError):
    """The command's inputs cannot be loaded (a missing directory, repeated database, ...)."""


class LowDiskStop(RuntimeError):
    """GraphDB refused a write because its volume is below the 5% hard floor."""

    def __init__(self, graph: str, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.graph = graph


class MetadataWriteFailed(RuntimeError):
    """The metadata graph could not be applied after the data graphs were written."""

    def __init__(self, graph: str, cause: BaseException, *, in_doubt: bool) -> None:
        super().__init__(str(cause))
        self.graph = graph
        self.in_doubt = in_doubt


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
    database's m018 and selection graphs and the metadata graph have been planned, so a refusal
    in a later graph cannot leave an earlier one in the store.
    """

    delivery: Delivery
    runs: list[tuple[WindowSource, Database, RunPlan, RunPlan]] = field(default_factory=list)
    statuses: dict[str, str] = field(default_factory=dict)
    refusals: dict[str, str] = field(default_factory=dict)
    metadata: MetadataProjection | None = None
    metadata_plan: gate.IngestPlan | None = None
    metadata_status: str | None = None


class Timings:
    """Print the elapsed time of each step and accumulate it per window."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.window_seconds: dict[str, float] = {}

    def stage(self, step: str, window: str | None = None) -> _Stage:
        return _Stage(self, step, window)

    def summary(self) -> None:
        total = time.perf_counter() - self.started
        print(f"\ntime: total {total:.2f} s")
        for window, seconds in self.window_seconds.items():
            print(f"time: window {window}: {seconds:.2f} s")


class _Stage:
    """A context manager that prints and records one timed step."""

    def __init__(self, timings: Timings, step: str, window: str | None) -> None:
        self.timings = timings
        self.step = step
        self.window = window
        self.started = 0.0

    def __enter__(self) -> Self:
        self.started = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        elapsed = time.perf_counter() - self.started
        where = f" ({self.window})" if self.window else ""
        print(f"time: {self.step}{where}: {elapsed:.2f} s", flush=True)
        if self.window:
            self.timings.window_seconds[self.window] = (
                self.timings.window_seconds.get(self.window, 0.0) + elapsed
            )


def _label(text: str) -> str:
    if not re.fullmatch(RUN_LABEL_PATTERN, text):
        raise argparse.ArgumentTypeError(
            f"run label {text!r} does not match {RUN_LABEL_PATTERN} (as in rule)"
        )
    return text


def _database_path(text: str) -> Path:
    return Path(text).resolve()


def _percentage(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a percentage") from exc
    if not 0 <= value <= _PERCENT:
        raise argparse.ArgumentTypeError("--min-free-pct must be between 0 and 100")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--label",
        required=True,
        type=_label,
        metavar="LABEL",
        help="the run family's label ([a-z][a-z0-9_]{1,31}, as in final)",
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
        help="a delivery folder of <label>_<window>.db files, SHA256SUMS and config_<label>.md",
    )
    parser.add_argument(
        "--windows",
        action="append",
        default=[],
        metavar="P1,H1",
        help="require these windows to be present (comma-separated or repeated)",
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="legacy pilot only: the folder has no SHA256SUMS (needs --no-config too)",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="legacy pilot only: the folder has no config_<label>.md (needs --no-manifest too)",
    )
    parser.add_argument(
        "--min-free-pct",
        type=_percentage,
        default=8.0,
        metavar="PCT",
        help="stop below this free percentage on GraphDB's volume (default 8; hard floor 5)",
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


def _dry_run(  # noqa: PLR0913, PLR0917 -- the projector inputs are explicit
    label: str,
    window: WindowSource,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
    timings: Timings,
) -> tuple[RunResult, RunResult]:
    database = Database(label, window.path)
    source = FinancialSource.open(window.path)
    try:
        with timings.stage("dry run m018", window.window):
            backtest = run(source, assets, guard_catalog, database.label)
        with timings.stage("dry run selection", window.window):
            selection = run_selection(source, assets, selection_catalog, database.label)
    finally:
        source.close()
    print(f"\ndry run m018: {window.path}")
    print(backtest.summary())
    problem = _failed(backtest)
    if problem is not None:
        raise LoadError(f"m018 dry run, {window.path}: {problem}")
    print(f"\ndry run selection: {window.path}")
    print(selection.summary())
    problem = _failed(selection)
    if problem is not None:
        raise LoadError(f"selection dry run, {window.path}: {problem}")
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


def _plan_metadata(
    preflight: Preflight,
    store: GraphDB,
    metadata: MetadataProjection,
    timings: Timings,
    disk: DiskMonitor,
) -> None:
    disk.check("pre-flight metadata")
    with timings.stage("pre-flight meta"):
        print(f"\npre-flight meta: {metadata.graph}")
        meta: MetaPlan = plan_meta(store, metadata)
        preflight.metadata = metadata
        preflight.metadata_status = meta.status
        preflight.statuses[metadata.graph] = meta.status
        print(f"  pre-flight {meta.status}: {metadata.graph}")
        if meta.status == REFUSED:
            why = meta.rejected or "refused"
            preflight.refusals[metadata.graph] = why
            print(f"    {why}")
        elif meta.status == ALREADY_IN_STORE:
            print(f"  already in the store: {metadata.graph}")
        else:
            preflight.metadata_plan = meta.plan
        print(f"  {metadata.triples} triples")


def _preflight(  # noqa: PLR0913, PLR0917 -- the pre-flight inputs are explicit
    delivery: Delivery,
    metadata: MetadataProjection | None,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
    store: GraphDB,
    timings: Timings,
    disk: DiskMonitor,
) -> Preflight:
    """Plan every m018, selection and metadata graph against the store before writing any."""
    print(
        "\npre-flight: gate.plan for every graph with the store's context (SELECT only); "
        "nothing is written"
    )
    preflight = Preflight(delivery)
    for window in delivery.windows:
        database = Database(delivery.label, window.path)
        disk.check(f"window {window.window}")
        with timings.stage("pre-flight", window.window):
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
        preflight.runs.append((window, database, backtest, selection))
    if metadata is not None:
        _plan_metadata(preflight, store, metadata, timings, disk)
    return preflight


def _preflight_rows(preflight: Preflight) -> list[TableRow]:
    rows: list[TableRow] = []
    for _, _, backtest, selection in preflight.runs:
        for planned in (backtest, selection):
            for graph in sorted(planned.result.graphs):
                rows.append(
                    TableRow(
                        graph,
                        planned.result.graphs[graph],
                        preflight.statuses.get(graph, WOULD_WRITE),
                    )
                )
    if preflight.metadata is not None:
        graph = preflight.metadata.graph
        rows.append(
            TableRow(
                graph,
                preflight.metadata.triples,
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


def _is_low_disk(exc: BaseException) -> bool:
    return _LOW_DISK in str(exc).lower()


def _pending_graph(planned: RunPlan) -> str:
    return next(
        (
            graph
            for graph in sorted(planned.plans)
            if graph not in planned.result.written and graph not in planned.result.rejected
        ),
        "",
    )


def _write_all(  # noqa: C901, PLR0912 -- one branch per write failure kind
    preflight: Preflight,
    store: GraphDB,
    written: list[str],
    timings: Timings,
    disk: DiskMonitor,
) -> None:
    """Apply the already-computed plans: every m018 graph, every selection sibling, then metadata."""
    for kind, position in (("m018", 0), ("selection", 1)):
        for window, database, backtest, selection in preflight.runs:
            planned = (backtest, selection)[position]
            disk.check(f"write {kind}: {database.path.name}")
            with timings.stage(f"write {kind}", window.window):
                print(f"\nwrite {kind}: {database.path}")
                try:
                    write_run(planned, store)
                except StoreInterrupted as exc:
                    written.extend(planned.result.written)
                    for graph in planned.result.written:
                        preflight.statuses[graph] = WRITTEN
                    if _is_low_disk(exc):
                        raise LowDiskStop(_pending_graph(planned), exc) from exc
                    raise
                print(planned.result.summary())
                written.extend(planned.result.written)
                for graph in planned.result.written:
                    preflight.statuses[graph] = WRITTEN
                problem = _failed(planned.result)
                if problem is not None:
                    raise LoadError(f"{kind} write, {database.path}: {problem}")
    if preflight.metadata is not None:
        graph = preflight.metadata.graph
        if preflight.metadata_plan is None:
            print(f"\nwrite meta: {graph}\n  already in the store: {graph}")
            return
        disk.check("write metadata", before_write=True)
        with timings.stage("write meta"):
            print(f"\nwrite meta: {graph}")
            try:
                count = write_metadata(store, preflight.metadata_plan)
            except gate.WriteInDoubt as exc:
                raise MetadataWriteFailed(graph, exc, in_doubt=True) from exc
            except gate.GraphDBError as exc:
                if _is_low_disk(exc):
                    raise LowDiskStop(graph, exc) from exc
                raise MetadataWriteFailed(graph, exc, in_doubt=False) from exc
            except gate.IngestRejected as exc:
                raise MetadataWriteFailed(graph, exc, in_doubt=False) from exc
            print(f"  written: {graph}: {count} triples")
            written.append(graph)
            preflight.statuses[graph] = WRITTEN


def _verify_graph(  # noqa: PLR0913, PLR0917 -- the verifier inputs are explicit
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


def _print_window_timings(delivery: Delivery, seconds: Mapping[str, float]) -> None:
    """Flag every window over 30 minutes in the run summary."""
    for window in delivery.windows:
        elapsed = seconds.get(window.window, 0.0)
        if elapsed > SLOW_WINDOW_SECONDS:
            line = (
                f"STOP AND ASK upstream: {window.window} took {elapsed / 60:.1f} min "
                f"(> {SLOW_WINDOW_SECONDS // 60} min)"
            )
            print(line)
            print(line, file=sys.stderr)


def _catalogs(
    args: argparse.Namespace,
    timings: Timings,
) -> tuple[Mapping[str, AssetInfo], GuardCatalog, SelectionRuleCatalog]:
    if args.contract:
        with timings.stage("view contract"):
            _view_contract(args.contract)
    with timings.stage("schema catalogs"):
        assets = universe_assets(config.universe_db_path())
        guard_catalog = load_guard_catalog(config.schema_dir() / "rules.ttl")
        selection_catalog = load_selection_catalog(config.schema_dir() / "rules.ttl")
    return assets, guard_catalog, selection_catalog


def _metadata(delivery: Delivery) -> MetadataProjection | None:
    if not delivery.metadata:
        return None
    assert delivery.config is not None  # Delivery.metadata requires it
    hashes = {window.path: window.sha256 or "" for window in delivery.windows}
    try:
        return validate_metadata(delivery.label, delivery.windows, hashes, delivery.config)
    except (MetadataError, gate.IngestRejected) as exc:
        raise LoadError(f"metadata graph, {delivery.label}: {exc}") from exc


def _prepare(
    args: argparse.Namespace,
    delivery: Delivery,
    metadata: MetadataProjection | None,
    timings: Timings,
) -> tuple[
    Mapping[str, AssetInfo],
    GuardCatalog,
    SelectionRuleCatalog,
    dict[Path, tuple[RunResult, RunResult]],
]:
    """Load the catalogs and dry-run every database."""
    assets, guard_catalog, selection_catalog = _catalogs(args, timings)
    dry: dict[Path, tuple[RunResult, RunResult]] = {}
    for window in delivery.windows:
        dry[window.path] = _dry_run(
            delivery.label, window, assets, guard_catalog, selection_catalog, timings
        )
    if metadata is not None:
        with timings.stage("dry run meta"):
            print(f"\ndry run meta: {metadata.graph}")
            print(f"  {metadata.triples} triples, SHACL-valid, not written")
    return assets, guard_catalog, selection_catalog, dry


def _open_check_store() -> GraphDB:
    """The read-only pre-flight's store; production is readable without the write opt-in."""
    return GraphDB.from_env()


def _verify_all(  # noqa: PLR0913, PLR0917 -- the verifier inputs are explicit
    preflight: Preflight,
    store: GraphDB,
    assets: Mapping[str, AssetInfo],
    guard_catalog: GuardCatalog,
    selection_catalog: SelectionRuleCatalog,
    timings: Timings,
) -> tuple[list[TableRow], bool]:
    """Verify every graph in turn and stop at the first failed check."""
    rows: list[TableRow] = []
    for window, database, backtest, selection in preflight.runs:
        for planned in (backtest, selection):
            for graph in sorted(planned.result.graphs):
                with timings.stage("verification", window.window):
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
    if preflight.metadata is not None:
        with timings.stage("verification meta"):
            verification = verify_metadata(
                store,
                preflight.metadata,
                repository=store.repository,
                host=store.host,
            )
            print(verification.summary())
        rows.append(
            TableRow(
                preflight.metadata.graph,
                verification.triples,
                preflight.statuses.get(preflight.metadata.graph, WRITTEN),
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
    if isinstance(exc, DiskSpaceError):
        print(f"disk error: {exc}", file=sys.stderr)
    elif isinstance(exc, (ContractFetchError, ExpectationError)):
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


def _report_low_disk(exc: LowDiskStop, written: Sequence[str]) -> None:
    print(
        f"\nSTOPPED: {exc}\n"
        f"graph being written: {exc.graph or '(unknown)'}\n"
        "GraphDB refuses every write below 5% free on its data volume. Free space, then drop "
        "the partial graph only if it exists and only after deciding the loss is acceptable:",
        file=sys.stderr,
    )
    _print_drops([*written, exc.graph] if exc.graph else written)


def _report_metadata_failure(exc: MetadataWriteFailed, written: Sequence[str]) -> None:
    print(
        f"\nstore error after the data writes: {exc}\n"
        f"metadata graph: {exc.graph}\n"
        + (
            "It is in doubt: the batch was sent but the store's answer was lost."
            if exc.in_doubt
            else "The store answered with an error before the metadata graph was written."
        ),
        file=sys.stderr,
    )
    _print_drops([*written, *([exc.graph] if exc.in_doubt else [])])


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
    MetadataError,
    DiskSpaceError,
    BoundaryError,
    ProjectionError,
    VerificationError,
    ContractFetchError,
    ExpectationError,
    gate.IngestRejected,
    sqlite3.Error,
    GraphDBError,
    OSError,
)


def main(  # noqa: C901, PLR0911, PLR0912, PLR0915 -- one branch per failure kind
    argv: Sequence[str] | None = None,
) -> int:
    args = parse_args(argv)
    written: list[str] = []
    preflight: Preflight | None = None
    delivery: Delivery | None = None
    timings = Timings()
    try:
        # Announce the target before any other output, without contacting the store: the delivery
        # manifest must still be verified before the first request. A dry run prints no banner.
        if args.check_store or args.write:
            announce_target(GraphDB.from_env())
        required_windows = parse_windows(args.windows)
        with timings.stage("delivery files"):
            delivery = load_delivery(
                args.label,
                args.db,
                args.dir,
                required_windows,
                no_manifest=args.no_manifest,
                no_config=args.no_config,
            )
        assert delivery is not None
        databases = [Database(delivery.label, window.path) for window in delivery.windows]
        _check_duplicate_graphs(databases)
        metadata = _metadata(delivery)
        if args.check_store:
            assets, guard_catalog, selection_catalog = _catalogs(args, timings)
            store = _open_check_store()
            disk = DiskMonitor(store, args.min_free_pct)
            disk.check("pre-flight", before_write=True)
            preflight = _preflight(
                delivery,
                metadata,
                assets,
                guard_catalog,
                selection_catalog,
                store,
                timings,
                disk,
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
        assets, guard_catalog, selection_catalog, dry = _prepare(args, delivery, metadata, timings)
        if not args.write:
            rows = [
                TableRow(graph, result.graphs[graph], DRY_RUN)
                for _, (backtest, selection) in dry.items()
                for result in (backtest, selection)
                for graph in sorted(result.graphs)
            ]
            if metadata is not None:
                rows.append(TableRow(metadata.graph, metadata.triples, DRY_RUN))
            _print_table(rows)
            return 0
        write_store = open_store(args)
        assert write_store is not None  # open_store only returns None without --write
        disk = DiskMonitor(write_store, args.min_free_pct)
        disk.check("before write", before_write=True)
        preflight = _preflight(
            delivery,
            metadata,
            assets,
            guard_catalog,
            selection_catalog,
            write_store,
            timings,
            disk,
        )
        if preflight.refusals:
            _print_table(_preflight_rows(preflight), note="not verified (pre-flight)")
            _report_preflight_refusals(preflight)
            return 1
        _write_all(preflight, write_store, written, timings, disk)
        rows, failed = _verify_all(
            preflight, write_store, assets, guard_catalog, selection_catalog, timings
        )
    except DeliveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LowDiskStop as exc:
        _report_low_disk(exc, written)
        return 1
    except MetadataWriteFailed as exc:
        _report_metadata_failure(exc, written)
        return 1
    except StoreInterrupted as exc:
        written.extend(exc.result.written)
        assert preflight is not None  # a write only happens after the pre-flight
        _report_interrupted(exc, preflight, written)
        return 1
    except _FAILURES as exc:
        return _report_failure(exc, written)
    finally:
        timings.summary()
        if delivery is not None:
            _print_window_timings(delivery, timings.window_seconds)
    _print_table(rows)
    if failed:
        _print_drops(written)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
