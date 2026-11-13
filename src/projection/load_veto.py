"""Load the final Veto Hierarchy delivery from ``manifest_final.json`` (T-865-T-869).

One command owns the whole delivery: verify the manifest and every file's SHA-256, filter the
configurations/windows, project meta + m018 + detail + selection per key, SHACL-validate each key,
then dry-run, pre-flight or append the graphs. It never deletes a graph and never appends to a
non-empty one; the human runs the DROP commands of the runbook.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyshacl
import rdflib

from etl import config
from kg_store import gate
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError, announce_target
from projection.backtest import (
    AssetInfo,
    GuardCatalog,
    ProjectionError,
    StoreInterrupted,
    load_guard_catalog,
    load_selection_catalog,
    project_selection_source,
    project_source,
    universe_assets,
    validation_context,
)
from projection.boundary import BoundaryError
from projection.control_counts import (
    ControlCountError,
    compare_control_counts,
    compute_control_counts,
    compute_series_counts,
    validate_control_counts,
    verify_store_control_counts,
)
from projection.delivery import ConfigError, read_config
from projection.disk_space import DiskMonitor, DiskSpaceError
from projection.run_metadata import MetadataError, RunInfo, build_metadata, read_run_info
from projection.source import FinancialSource
from projection.veto_events import (
    DetailError,
    DetailFile,
    parse_detail_file,
    read_asset_tickers,
    read_rankings,
    selection_index,
)
from projection.veto_manifest import (
    VetoManifest,
    VetoManifestError,
    backtest_graph_name,
    read_manifest,
    selection_graph_name,
    verify_files,
)

SHAPES = "shapes.ttl"


class LoadVetoError(ValueError):
    """A loader step failed; the message names the step and the source."""


class WriteFailed(LoadVetoError):
    """A write stopped partway; ``written`` lists every graph already appended."""

    def __init__(
        self, message: str, written: Sequence[str], *, in_doubt: str | None = None
    ) -> None:
        super().__init__(message)
        self.written = tuple(written)
        self.in_doubt = in_doubt


@dataclass(frozen=True)
class VetoGraph:
    """One graph of the delivery and its projected bytes."""

    graph: str
    data: bytes
    triples: int
    kind: str
    configuration: str | None
    window: str | None


@dataclass
class VetoBatch:
    """The meta graph and the m018/selection graphs of one manifest key."""

    key: tuple[str, str, str]
    graphs: list[VetoGraph]
    m018: rdflib.Graph
    selection: rdflib.Graph | None = None
    detail: DetailFile | None = None


@dataclass(frozen=True)
class LoadResult:
    """What a dry run/pre-flight/write produced."""

    batches: tuple[VetoBatch, ...]
    meta: VetoGraph
    written: tuple[str, ...] = ()
    in_doubt: str | None = None


def _graph_bytes(graph: rdflib.Graph) -> bytes:
    return graph.serialize(format="turtle").encode()


def _triples(graph: rdflib.Graph) -> int:
    return len(graph)


def _merge(graphs: Sequence[rdflib.Graph]) -> rdflib.Graph:
    out = rdflib.Graph()
    for graph in graphs:
        for triple in graph:
            out.add(triple)
    return out


def _config_assets(path: Path | None) -> Mapping[str, AssetInfo]:
    if path is None or not path.is_file():
        raise LoadVetoError(
            f"{path}: the universe database is missing; set SQL_UNIVERSE_DB to the final catalog"
        )
    return universe_assets(path)


def _read_detail(run_files: Mapping[str, Path]) -> DetailFile | None:
    path = run_files.get("jsonl_file")
    return parse_detail_file(path) if path is not None else None


def _run_info(path: Path, label: str, configuration: str) -> RunInfo:
    info = read_run_info(path, label)
    return dataclasses.replace(info, configuration=configuration)


def build_delivery(  # noqa: C901, PLR0912, PLR0915 -- one branch per graph kind
    manifest: VetoManifest,
    label: str,
    *,
    assets_db: Path | None = None,
    validate_shacl: bool = True,
) -> LoadResult:
    """Verify the manifest, project every graph and optionally SHACL-validate each key."""
    if manifest.label != label:
        raise LoadVetoError(
            f"{manifest.path}: label {manifest.label!r} differs from --label {label!r}"
        )
    try:
        hashes = verify_files(manifest)
    except VetoManifestError as exc:
        for run in manifest.engine_runs:
            for path in run.files.values():
                if str(path) in str(exc) or path.name in str(exc):
                    raise LoadVetoError(f"{run.configuration}/{run.window}: {exc}") from exc
        raise
    validate_control_counts(
        manifest.control_counts,
        tuple(dict.fromkeys(run.configuration for run in manifest.runs)),
        manifest.windows,
        final=not manifest.draft,
    )
    print(f"\nmanifest: {manifest.path} ({manifest.status or 'final'})")
    print(f"manifest: {len(hashes)} file(s) verified")
    if assets_db is None:
        assets_db = config.universe_db_path()
    assets = _config_assets(assets_db)
    guard_catalog = load_guard_catalog(config.schema_dir() / "rules.ttl")
    selection_catalog = load_selection_catalog(config.schema_dir() / "rules.ttl")
    config_path = manifest.root / f"config_{label}.md"
    if not config_path.is_file():
        raise LoadVetoError(
            f"{config_path}: the metadata graph needs the frozen config_{label}.md next to the manifest"
        )
    run_config = read_config(config_path, label)
    runs = [_run_info(run.db_file, label, run.configuration) for run in manifest.engine_runs]
    meta_projection = build_metadata(label, runs, hashes, run_config)
    meta = VetoGraph(
        meta_projection.graph,
        meta_projection.data,
        meta_projection.triples,
        "meta",
        None,
        None,
    )
    batches: list[VetoBatch] = []
    for run in manifest.engine_runs:
        source = FinancialSource.open(run.db_file)
        try:
            if run.configuration.startswith("SYSTEM_") and not manifest.draft:
                if "jsonl_file" not in run.files:
                    raise LoadVetoError(
                        f"{run.db_file}: {run.configuration}/{run.window} has no jsonl_file; "
                        "every final System run ships its detail file"
                    )
                if "rankings_file" not in run.files:
                    raise LoadVetoError(
                        f"{run.db_file}: {run.configuration}/{run.window} has no rankings_file; "
                        "every final System run ships its rankings JSON"
                    )
                if "scales_file" not in run.files:
                    raise LoadVetoError(
                        f"{run.db_file}: {run.configuration}/{run.window} has no scales_file; "
                        "every final System run ships its scales JSON"
                    )
            detail = _read_detail(run.files)
            tickers = read_asset_tickers(source)
            rankings = None
            if "rankings_file" in run.files:
                rankings = read_rankings(run.files["rankings_file"])
            selection = None
            if run.configuration.startswith("SYSTEM_") and detail is not None:
                if rankings is None:
                    raise LoadVetoError(
                        f"{run.db_file}: {run.configuration}/{run.window} has no rankings_file; "
                        "every System run that enters the graph must ship its rankings JSON"
                    )
                dates = [str(line["date"]) for line in detail.decisions]
                if not dates:
                    dates = [str(line["date"]) for line in detail.retention_decisions]
                selection = selection_index(source, label, run.window, run.configuration, dates)
            m018_projection = project_source(
                source,
                assets,
                guard_catalog,
                label,
                configuration=run.configuration,
                window=run.window,
                book_code=run.book_code,
                book_id=run.book_id,
                detail=detail,
                asset_tickers=tickers,
                selection=selection,
                rankings_by_date=rankings,
            )
            graph_name = backtest_graph_name(label, run.window, run.configuration)
            m018 = rdflib.Graph().parse(
                data=m018_projection.projection.turtle(graph_name), format="turtle"
            )
            graphs = [
                VetoGraph(
                    graph_name,
                    _graph_bytes(m018),
                    _triples(m018),
                    "m018",
                    run.configuration,
                    run.window,
                )
            ]
            selection_graph = None
            if run.configuration.startswith("SYSTEM_"):
                selection_projection = project_selection_source(
                    source,
                    assets,
                    selection_catalog,
                    label,
                    configuration=run.configuration,
                )
                selection_name = selection_graph_name(label, run.window, run.configuration)
                selection_graph = rdflib.Graph().parse(
                    data=selection_projection.projection.turtle(selection_name), format="turtle"
                )
                graphs.append(
                    VetoGraph(
                        selection_name,
                        _graph_bytes(selection_graph),
                        _triples(selection_graph),
                        "selection",
                        run.configuration,
                        run.window,
                    )
                )
            detail_rows: Mapping[str, int]
            if m018_projection.projection.detail is not None:
                detail_rows = m018_projection.projection.detail.rows
            else:
                detail_rows = {}
                if not manifest.draft:
                    raise LoadVetoError(f"{run.db_file}: the detail projection is missing")
            if not manifest.draft and not _has_control_counts(
                manifest, run.configuration, run.window
            ):
                raise LoadVetoError(f"{run.configuration}/{run.window}: control_counts is missing")
            if _has_control_counts(manifest, run.configuration, run.window) or not manifest.draft:
                computed = compute_control_counts(
                    run.configuration,
                    run.window,
                    rows=m018_projection.rows,
                    detail=detail,
                    memory_rows=detail_rows,
                    rankings=rankings,
                    files=run.files,
                )
                compare_control_counts(
                    manifest.control_counts,
                    run.configuration,
                    run.window,
                    computed,
                    final=not manifest.draft,
                )
            else:
                print(f"control counts not provided for {run.configuration}/{run.window}")
            batch = VetoBatch(
                (label, run.configuration, run.window),
                graphs,
                m018,
                selection_graph,
                detail,
            )
            batches.append(batch)
        finally:
            source.close()
    if validate_shacl:
        _validate_batches(batches, assets, guard_catalog)
        _validate_meta(meta, assets, guard_catalog)
    for run in manifest.runs:
        if run.source_kind != "series_csv":
            continue
        if not manifest.draft and not _has_control_counts(manifest, run.configuration, run.window):
            raise LoadVetoError(f"{run.configuration}/{run.window}: control_counts is missing")
        if _has_control_counts(manifest, run.configuration, run.window) or not manifest.draft:
            computed = compute_series_counts(
                run.window, run.files, window_filter=run.configuration == "SPY"
            )
            compare_control_counts(
                manifest.control_counts,
                run.configuration,
                run.window,
                computed,
                final=not manifest.draft,
            )
        else:
            print(f"control counts not provided for {run.configuration}/{run.window}")
    print("\nprojected graphs:")
    for graph in (meta, *(item for batch in batches for item in batch.graphs)):
        print(f"  {graph.kind:9} {graph.graph}: {graph.triples} triples")
    return LoadResult(tuple(batches), meta)


def _validate_batches(
    batches: Sequence[VetoBatch], assets: Mapping[str, AssetInfo], catalog: GuardCatalog
) -> None:
    shapes = rdflib.Graph().parse(config.schema_dir() / SHAPES, format="turtle")
    context = rdflib.Graph()
    for triple in validation_context(assets, catalog):
        context.add(triple)
    _add_configurations(context)
    for batch in batches:
        graph = _merge([batch.m018, *([batch.selection] if batch.selection is not None else [])])
        for triple in context:
            graph.add(triple)
        conforms, results, _ = pyshacl.validate(graph, shacl_graph=shapes)
        if not conforms:
            raise LoadVetoError(
                f"SHACL failed for {batch.key[1]}/{batch.key[2]}:\n"
                + results.serialize(format="turtle")[:8000]
            )
        print(f"SHACL: {batch.key[1]}/{batch.key[2]} conforms")


def _validate_meta(meta: VetoGraph, assets: Mapping[str, AssetInfo], catalog: GuardCatalog) -> None:
    shapes = rdflib.Graph().parse(config.schema_dir() / SHAPES, format="turtle")
    graph = rdflib.Graph().parse(data=meta.data, format="turtle")
    for triple in validation_context(assets, catalog):
        graph.add(triple)
    _add_configurations(graph)
    conforms, results, _ = pyshacl.validate(graph, shacl_graph=shapes)
    if not conforms:
        raise LoadVetoError(
            "SHACL failed for the metadata graph:\n" + results.serialize(format="turtle")[:8000]
        )
    print("SHACL: meta conforms")


def _add_configurations(graph: rdflib.Graph) -> None:
    """Add the TBox (classes, subclasses and the five configuration individuals) as context."""
    tbox = rdflib.Graph().parse(config.schema_dir() / "tbox.ttl", format="turtle")
    for triple in tbox:
        graph.add(triple)


def _existing(store: GraphDB, graph: str) -> int:
    rows = store.select(f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}")
    try:
        return int(rows[0]["n"])
    except (IndexError, KeyError, ValueError):
        return 0


def _all_graphs(result: LoadResult) -> list[VetoGraph]:
    return [result.meta, *(graph for batch in result.batches for graph in batch.graphs)]


def plan_delivery(
    store: GraphDB, result: LoadResult, *, minimum_free_pct: float = 8.0
) -> list[gate.IngestPlan]:
    """Plan every graph with ``gate.plan``; refuse any existing non-empty graph."""
    disk = DiskMonitor(store, minimum_free_pct)
    plans: list[gate.IngestPlan] = []
    for graph in _all_graphs(result):
        count = _existing(store, graph.graph)
        if count:
            raise LoadVetoError(
                f"{graph.graph}: already holds {count} triples; the loader never appends. "
                "DROP the graph first (runbook, one graph at a time)."
            )
        disk.check(f"pre-flight {graph.graph}")
        try:
            plan = gate.plan(store, graph.data, graph.graph)
        except gate.IngestRejected as exc:
            raise LoadVetoError(f"{graph.graph}: {exc}") from exc
        print(f"pre-flight: {graph.graph}: {plan.status.value}, {graph.triples} triples")
        plans.append(plan)
    return plans


def write_delivery(
    store: GraphDB, plans: Sequence[gate.IngestPlan]
) -> tuple[tuple[str, ...], str | None]:
    """Apply an already-computed plan list one graph at a time; never plan or drop twice."""
    written: list[str] = []
    in_doubt: str | None = None
    for plan in plans:
        try:
            gate.write(store, plan)
        except gate.WriteInDoubt:
            in_doubt = plan.graph
            break
        except gate.IngestRejected as exc:
            raise WriteFailed(f"{plan.graph}: {exc}", written) from exc
        except GraphDBError as exc:
            raise WriteFailed(f"{plan.graph}: {exc}", written) from exc
        written.append(plan.graph)
        print(f"written: {plan.graph}")
    return tuple(written), in_doubt


def verify_delivery(  # noqa: C901 -- one check per graph family
    store: GraphDB, result: LoadResult, manifest: VetoManifest
) -> None:
    """Read-only count and price/removed-rule checks against the manifest control counts."""
    failures: list[str] = []
    for item in _all_graphs(result):
        count = _existing(store, item.graph)
        if count != item.triples:
            failures.append(f"{item.graph}: stored {count}, projected {item.triples}")
    expected = _control_counts(manifest)
    if expected:
        for graph_name, count in expected.items():
            actual = _existing(store, graph_name)
            if actual != count:
                failures.append(f"{graph_name}: control count {count}, stored {actual}")
    for batch in result.batches:
        failures.extend(
            verify_store_control_counts(
                store,
                batch.graphs[0].graph,
                batch.key[1],
                batch.key[2],
                manifest.control_counts,
            )
        )
    for run in getattr(manifest, "runs", ()):
        if run.source_kind == "series_csv":
            print(
                f"control count not store-verifiable: {run.configuration}/{run.window}.daily_rows: "
                "the reference series CSV is not loaded"
            )
    old_rules = _old_rule_alerts(store)
    if old_rules:
        failures.append("removed rules still referenced: " + ", ".join(old_rules))
    prices = _price_properties(store)
    if prices:
        failures.append("price properties on L1_BP alerts: " + ", ".join(prices))
    masked = _masked_asset_prices(store)
    if masked:
        failures.append("price properties on masked assets: " + ", ".join(masked))
    if failures:
        raise LoadVetoError("verification failed:\n" + "\n".join(f"  {line}" for line in failures))
    print("verification: stored counts, control counts and removed-rule/price checks pass")


_PREFIX = "PREFIX : <https://thesis.local/kg/portfolio#>\n"


def _old_rule_alerts(store: GraphDB) -> list[str]:
    rows = store.select(
        _PREFIX + "SELECT DISTINCT ?graph ?rule WHERE { GRAPH ?graph { ?alert :alertRule ?rule } "
        "FILTER (?rule IN (:Rule_L1_STOP_LOSS, :Rule_L1_REENTRY, :Rule_L2_NEWS, :Rule_L3_VOL, :Rule_L4_DD)) }"
    )
    return [f"{row.get('graph')}:{row.get('rule')}" for row in rows]


def _masked_asset_prices(store: GraphDB) -> list[str]:
    rows = store.select(
        _PREFIX
        + "SELECT DISTINCT ?graph ?asset ?p WHERE { GRAPH ?graph { ?asset :pricesNotPublished true ; ?p ?v . "
        "FILTER (?p IN (:alertValue, :alertThreshold, :stopDistancePct, :closePrice, :dailyReturn)) } }"
    )
    return [f"{row.get('graph')}:{row.get('asset')}:{row.get('p')}" for row in rows]


def _price_properties(store: GraphDB) -> list[str]:
    rows = store.select(
        _PREFIX
        + "SELECT DISTINCT ?graph ?alert ?p WHERE { GRAPH ?graph { ?alert :alertRule ?rule . "
        "?alert ?p ?v . FILTER (STRSTARTS(STR(?rule), STR(:Rule_L1_BP_))) "
        "FILTER (?p IN (:alertValue, :alertThreshold)) } }"
    )
    return [f"{row.get('graph')}:{row.get('alert')}:{row.get('p')}" for row in rows]


def _has_control_counts(manifest: VetoManifest, configuration: str, window: str) -> bool:
    value = manifest.control_counts
    if not isinstance(value, dict):
        return False
    configurations = value.get("configurations", value)
    if not isinstance(configurations, dict):
        return False
    windows = configurations.get(configuration)
    return isinstance(windows, dict) and window in windows


def _control_counts(  # noqa: C901, PLR0912 -- two accepted manifest shapes
    manifest: VetoManifest,
) -> Mapping[str, int]:
    """Read the optional control counts as ``{graph: triples}``.

    Two shapes are accepted: ``{"graphs": {iri: count}}`` and the per-key shape
    ``{"configurations": {configuration: {window: {"m018": n, "selection": n}}}}``. Anything else
    is reported as not machine-readable rather than guessed.
    """
    value = manifest.control_counts
    if not isinstance(value, dict):
        print("control counts: not provided (draft or free-form); using projected counts")
        return {}
    graphs = value.get("graphs")
    if isinstance(graphs, dict):
        return {str(graph): int(count) for graph, count in graphs.items()}
    configurations = value.get("configurations", value)
    out: dict[str, int] = {}
    if not isinstance(configurations, dict):
        print(
            "control counts: not provided as a graph or per-configuration map; using projected counts"
        )
        return {}
    for configuration, windows in configurations.items():
        if configuration not in (
            "SYSTEM_WITH_HIERARCHY",
            "SYSTEM_WITHOUT_HIERARCHY",
            "MARKOWITZ_BASE",
        ):
            continue
        if not isinstance(windows, dict):
            continue
        for window, counts in windows.items():
            if not isinstance(counts, dict):
                continue
            for kind, count in counts.items():
                key = str(kind).lower()
                try:
                    number = int(count)
                except (TypeError, ValueError):
                    continue
                if key in ("m018", "m018_triples"):
                    out[backtest_graph_name(manifest.label, str(window), configuration)] = number
                elif key in ("selection", "selection_triples"):
                    out[selection_graph_name(manifest.label, str(window), configuration)] = number
                elif key in ("meta", "meta_triples"):
                    out[f"urn:graph:derived:backtest:meta:{manifest.label}"] = number
    return out


def verify_manifest_store(
    store: GraphDB,
    manifest: VetoManifest,
    label: str,
    *,
    assets_db: Path | None = None,
) -> None:
    """Re-project the manifest and run the read-only store checks (no write, no DROP)."""
    result = build_delivery(manifest, label, assets_db=assets_db)
    verify_delivery(store, result, manifest)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--manifest", required=True, type=Path, help="path to manifest_final.json")
    parser.add_argument("--label", default="final", help="run label (default: final)")
    parser.add_argument("--check-store", action="store_true", help="read-only pre-flight; no write")
    parser.add_argument("--write", action="store_true", help="append the graphs")
    parser.add_argument("--to-production", action="store_true", help="allow --write to production")
    parser.add_argument(
        "--min-free-pct", type=float, default=8.0, help="free-disk guard percentage"
    )
    args = parser.parse_args(argv)
    if args.check_store and args.write:
        parser.error("--check-store only reads; do not combine it with --write")
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    return args


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911 -- one return per mode
    args = parse_args(argv)
    try:
        manifest = read_manifest(args.manifest)
        result = build_delivery(manifest, args.label)
        if args.check_store:
            store = GraphDB.from_env()
            announce_target(store)
            plan_delivery(store, result, minimum_free_pct=args.min_free_pct)
            print("pre-flight complete: nothing was written")
            return 0
        if not args.write:
            print("dry run complete: no store was contacted")
            return 0
        store = GraphDB.from_env()
        announce_target(store)
        if store.repository == PRODUCTION_REPOSITORY and not args.to_production:
            print(
                "--write to the production repository needs --to-production (a maintainer decision)",
                file=sys.stderr,
            )
            return 2
        if store.repository == PRODUCTION_REPOSITORY and manifest.draft:
            print("STOPPED: a draft manifest cannot be written to production", file=sys.stderr)
            return 2
        plans = plan_delivery(store, result, minimum_free_pct=args.min_free_pct)
        try:
            written, in_doubt = write_delivery(store, plans)
        except WriteFailed as exc:
            print(
                "STOPPED: write failed; already written: "
                + (", ".join(exc.written) or "none")
                + (f"; in doubt: {exc.in_doubt}" if exc.in_doubt else ""),
                file=sys.stderr,
            )
            return 1
        if in_doubt:
            print(
                "STOPPED: write in doubt for "
                + in_doubt
                + "; already written: "
                + (", ".join(written) or "none")
                + f"\nThe maintainer may run: DROP GRAPH <{in_doubt}>",
                file=sys.stderr,
            )
            return 1
        verify_delivery(store, result, manifest)
        print(f"write complete: {len(written)} graph(s), no graph dropped")
        return 0  # noqa: TRY300 -- the success return pairs with the failure handlers
    except (
        VetoManifestError,
        DetailError,
        LoadVetoError,
        ConfigError,
        MetadataError,
        BoundaryError,
        ProjectionError,
        DiskSpaceError,
        ControlCountError,
        OSError,
    ) as exc:
        print(f"STOPPED\n{exc}", file=sys.stderr)
        return 1
    except StoreInterrupted as exc:
        print(f"STOPPED: store failure; written: {exc.result.written}", file=sys.stderr)
        return 1
    except GraphDBError as exc:
        print(f"STOPPED: store error: {exc}", file=sys.stderr)
        return 1
