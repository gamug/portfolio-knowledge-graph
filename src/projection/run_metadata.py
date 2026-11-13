"""Run metadata for a backtest delivery: build, write and verify the meta graph (Work item 35).

The delivery graph ``urn:graph:derived:backtest:meta:{label}`` holds one ``:BacktestRun`` per
window (the source file, its verified lowercase SHA-256, the run id, the window id, the run's
knowledge date and a link to its configuration) and one ``:RunConfiguration`` per label (the
front-matter fields and the frozen body as ``rdfs:comment``). The graph is append-only and goes
through the same ingest gate as the m018 and selection graphs.

The post-write verifier is deliberately separate from ``projection.verify_backtest``: it reads the
meta graph with ``SELECT`` only and proves the three things the delivery contract adds -- every
window's stored hash equals its manifest hash, exactly one configuration exists, and every window
has its run linked to that configuration.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, XSD

from kg_store import gate
from kg_store.graphdb import GraphDB
from projection.backtest import read_view
from projection.delivery import RunConfig, WindowSource
from projection.source import FinancialSource
from projection.verify_backtest import Check, ReadableStore, Verification
from projection.veto_manifest import configuration_iri, configuration_slug

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
META_GRAPH_PREFIX = "urn:graph:derived:backtest:meta:"
_LABEL = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PREFIXES = f"PREFIX : <{KG}>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"


class MetadataError(ValueError):
    """The delivery's run metadata cannot be built or does not match the manifest."""


@dataclass(frozen=True)
class RunInfo:
    """The one run a database describes (``v_book``): window, date range and knowledge date."""

    path: Path
    label: str
    window: str
    date_from: str
    date_to: str
    run_id: int
    knowledge_date: str
    configuration: str | None = None


@dataclass(frozen=True)
class MetadataProjection:
    """The complete meta graph for one delivery, before the gate sees it."""

    graph: str
    data: bytes
    triples: int
    label: str
    runs: tuple[RunInfo | WindowSource, ...]
    hashes: Mapping[Path, str]
    config: RunConfig


@dataclass(frozen=True)
class MetaPlan:
    """The metadata graph after ``gate.plan``: its projection and what a write would do."""

    projection: MetadataProjection
    status: str
    plan: gate.IngestPlan | None = None
    rejected: str | None = None

    @property
    def graph(self) -> str:
        return self.projection.graph

    @property
    def triples(self) -> int:
        return self.projection.triples


def meta_graph_name(label: str) -> str:
    """The append-only metadata graph of one run label."""
    if not _LABEL.fullmatch(label):
        raise MetadataError(f"run label {label!r} does not match {_LABEL.pattern}")
    return f"{META_GRAPH_PREFIX}{label}"


def read_run_info(path: Path, label: str) -> RunInfo:
    """Read ``v_book`` and assert one window, run id, knowledge date and date range.

    Different books of the same run repeat the run columns; two distinct values mean the database
    holds more than one run and the delivery cannot name a single ``:BacktestRun`` for it.
    """
    source = FinancialSource.open(path)
    try:
        rows = read_view(source, "v_book")
    finally:
        source.close()
    if not rows:
        raise MetadataError(f"{path}: v_book is empty, so the run has no window or knowledge date")
    window = _one(rows, "window_id", path)
    run_id = _one(rows, "backtest_run_id", path)
    knowledge = _one(rows, "knowledge_date", path)
    date_from = _one(rows, "d_start", path)
    date_to = _one(rows, "d_end", path)
    try:
        run = int(run_id)
    except ValueError:
        raise MetadataError(f"{path}: backtest_run_id {run_id!r} is not an integer") from None
    if run < 1:
        raise MetadataError(f"{path}: backtest_run_id {run_id!r} is not positive")
    _calendar(path, "knowledge_date", knowledge)
    opened = _calendar(path, "d_start", date_from)
    closed = _calendar(path, "d_end", date_to)
    if opened > closed:
        raise MetadataError(f"{path}: d_start {date_from} is after d_end {date_to}")
    return RunInfo(path, label, window, date_from, date_to, run, knowledge)


def _one(rows: Sequence[Mapping[str, object]], column: str, path: Path) -> str:
    values = {str(row.get(column)) for row in rows if row.get(column) is not None}
    if not values:
        raise MetadataError(f"{path}: v_book.{column} is NULL")
    if len(values) > 1:
        raise MetadataError(
            f"{path}: v_book.{column} has {len(values)} distinct values "
            f"({', '.join(sorted(values))}); one database must describe one run"
        )
    return next(iter(values))


def _calendar(path: Path, column: str, value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise MetadataError(f"{path}: v_book.{column} {value!r} is not a calendar date") from None


def build_metadata(  # noqa: C901, PLR0912, PLR0915 -- one branch per metadata field
    label: str,
    runs: Sequence[RunInfo | WindowSource],
    hashes: Mapping[Path, str],
    config: RunConfig,
) -> MetadataProjection:
    """Build the deterministic meta graph for every window of one delivery."""
    if not runs:
        raise MetadataError("no window to put in the metadata graph")
    configured = [run for run in runs if getattr(run, "configuration", None) is not None]
    if configured and len(configured) != len(runs):
        raise MetadataError("some runs carry a configuration and some do not")
    if configured:
        keys = [(str(run.configuration), run.window) for run in runs]
        if len(set(keys)) != len(keys):
            duplicates = sorted({key for key in keys if keys.count(key) > 1})
            raise MetadataError("two runs share a (configuration, window) key: " + repr(duplicates))
    else:
        windows = [run.window for run in runs]
        if len(set(windows)) != len(windows):
            raise MetadataError("two runs share a window id: " + ", ".join(sorted(windows)))
    graph = meta_graph_name(label)
    config_iri = KG[f"RunConfiguration_{label}"]
    out = rdflib.Graph()
    out.bind("", KG)
    out.add((config_iri, RDF.type, KG.RunConfiguration))
    out.add((config_iri, KG.runLabel, rdflib.Literal(label)))
    out.add((config_iri, KG.configCodeCommit, rdflib.Literal(config.code_commit)))
    out.add((config_iri, KG.configPr, rdflib.Literal(config.pr)))
    out.add((config_iri, KG.configResultsDoc, rdflib.Literal(config.results_doc)))
    if config.config_id is not None:
        out.add((config_iri, KG.configId, rdflib.Literal(config.config_id)))
    if config.status is not None:
        out.add((config_iri, KG.configStatus, rdflib.Literal(config.status)))
    out.add((config_iri, RDFS.comment, rdflib.Literal(config.body)))
    for run in runs:
        digest = hashes.get(run.path)
        if digest is None:
            raise MetadataError(f"{run.path}: no verified SHA-256 for the metadata graph")
        digest = digest.lower()
        if not _SHA256.fullmatch(digest):
            raise MetadataError(f"{run.path}: {digest!r} is not a lowercase SHA-256")
        configuration = getattr(run, "configuration", None)
        if configuration is None:
            iri = KG[f"BacktestRun_{label}_{run.window}"]
        else:
            iri = KG[f"Run_{label}_{run.window}_{configuration_slug(configuration)}"]
        out.add((iri, RDF.type, KG.BacktestRun))
        out.add((iri, KG.runLabel, rdflib.Literal(label)))
        out.add((iri, KG.windowId, rdflib.Literal(run.window)))
        if configuration is not None:
            out.add((iri, KG.configuration, KG[configuration_iri(configuration)]))
        out.add((iri, KG.backtestRunId, rdflib.Literal(run.run_id)))
        out.add((iri, KG.sourceFile, rdflib.Literal(run.path.name)))
        out.add((iri, KG.sourceSha256, rdflib.Literal(digest)))
        out.add(
            (
                iri,
                KG.knowledgeDate,
                rdflib.Literal(run.knowledge_date, datatype=XSD.date),
            )
        )
        out.add((iri, KG.runConfiguration, config_iri))
    data = out.serialize(format="turtle").encode()
    return MetadataProjection(graph, data, len(out), label, tuple(runs), dict(hashes), config)


def verify_metadata(
    store: ReadableStore,
    projection: MetadataProjection,
    *,
    repository: str = "",
    host: str = "",
) -> Verification:
    """Read the stored meta graph and prove its hashes, configuration and per-window runs."""
    graph = projection.graph
    triples = _count(store, f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}")
    rows = store.select(
        _PREFIXES
        + "SELECT ?run ?window ?run_id ?file ?sha ?knowledge ?config ?configuration WHERE { "
        + f"GRAPH <{graph}> {{ "
        + "?run a :BacktestRun ; :windowId ?window ; :backtestRunId ?run_id ; "
        + ":sourceFile ?file ; :sourceSha256 ?sha ; :knowledgeDate ?knowledge ; "
        + ":runConfiguration ?config . "
        + "OPTIONAL { ?run :configuration ?configuration } } }"
    )
    configured = any(getattr(run, "configuration", None) is not None for run in projection.runs)
    by_key: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_key.setdefault(_stored_key(row, configured), []).append(row)
    checks = [
        Check(
            "metadata graph name",
            graph == meta_graph_name(projection.label),
            f"stored {graph}",
        ),
        Check(
            "metadata triple count",
            triples == projection.triples,
            f"stored {triples:,}, expected {projection.triples:,}",
        ),
    ]
    expected_keys = [_run_key(run, configured) for run in projection.runs]
    checks.append(
        Check(
            "one BacktestRun per configuration/window"
            if configured
            else "one BacktestRun per window",
            sorted(by_key) == sorted(expected_keys)
            and all(len(by_key[key]) == 1 for key in expected_keys),
            "stored keys: " + (", ".join(sorted(by_key)) or "none"),
        )
    )
    config_iris = {row.get("config", "") for row in rows if row.get("config")}
    config_iri = str(KG[f"RunConfiguration_{projection.label}"])
    checks.append(
        Check(
            "every run links to one RunConfiguration",
            len(config_iris) == 1 and config_iris == {config_iri},
            "linked configurations: " + (", ".join(sorted(config_iris)) or "none"),
        )
    )
    for run in projection.runs:
        stored = by_key.get(_run_key(run, configured), [])
        name = _run_display(run, configured)
        expected_sha = projection.hashes[run.path].lower()
        expected_configuration = getattr(run, "configuration", None)
        if expected_configuration is not None:
            checks.append(
                Check(
                    f"configuration {name}",
                    len(stored) == 1
                    and stored[0].get("configuration", "")
                    == configuration_iri(expected_configuration),
                    f"stored {_one_value(stored, 'configuration')}, expected "
                    f"{configuration_iri(expected_configuration)}",
                )
            )
        checks.append(
            Check(
                f"source hash {name}",
                len(stored) == 1 and stored[0].get("sha") == expected_sha,
                f"stored {_one_value(stored, 'sha')}, expected {expected_sha}",
            )
        )
        checks.append(
            Check(
                f"source file {name}",
                len(stored) == 1 and stored[0].get("file") == run.path.name,
                f"stored {_one_value(stored, 'file')}, expected {run.path.name}",
            )
        )
        checks.append(
            Check(
                f"knowledge date {name}",
                len(stored) == 1 and stored[0].get("knowledge") == run.knowledge_date,
                f"stored {_one_value(stored, 'knowledge')}, expected {run.knowledge_date}",
            )
        )
        checks.append(
            Check(
                f"run id {name}",
                len(stored) == 1 and stored[0].get("run_id") == str(run.run_id),
                f"stored {_one_value(stored, 'run_id')}, expected {run.run_id}",
            )
        )
    configurations = _read_configuration(store, graph)
    checks.append(
        Check(
            "one RunConfiguration",
            len(configurations) == 1,
            f"stored {len(configurations)}",
        )
    )
    checks.extend(_configuration_checks(configurations, projection.config))
    return Verification(
        repository,
        host,
        graph,
        projection.label,
        projection.config.path,
        checks,
        triples,
    )


def _run_key(run: RunInfo | WindowSource, configured: bool) -> str:
    configuration = getattr(run, "configuration", None)
    return f"{configuration}/{run.window}" if configured else run.window


def _stored_key(row: Mapping[str, str], configured: bool) -> str:
    if configured:
        return f"{row.get('configuration', '')}/{row.get('window', '')}"
    return row.get("window", "")


def _run_display(run: RunInfo | WindowSource, configured: bool) -> str:
    if not configured:
        return run.window
    return f"{getattr(run, 'configuration', '')}/{run.window}"


def _read_configuration(store: ReadableStore, graph: str) -> list[dict[str, str]]:
    return store.select(
        _PREFIXES
        + "SELECT ?config ?label ?commit ?pr ?doc ?config_id ?status ?comment WHERE { "
        + f"GRAPH <{graph}> {{ "
        + "?config a :RunConfiguration ; :runLabel ?label ; :configCodeCommit ?commit ; "
        + ":configPr ?pr ; :configResultsDoc ?doc ; rdfs:comment ?comment . "
        + "OPTIONAL { ?config :configId ?config_id } "
        + "OPTIONAL { ?config :configStatus ?status } } }"
    )


def _configuration_checks(rows: Sequence[Mapping[str, str]], config: RunConfig) -> list[Check]:
    if len(rows) != 1:
        return [
            Check(
                "RunConfiguration fields",
                False,
                "no single configuration row to compare",
            )
        ]
    row = rows[0]
    expected = {
        "label": config.label,
        "commit": config.code_commit,
        "pr": config.pr,
        "doc": config.results_doc,
        "config_id": config.config_id or "",
        "status": config.status or "",
        "comment": config.body,
    }
    actual = {key: row.get(key, "") for key in expected}
    wrong = [key for key in expected if actual[key] != expected[key]]
    return [
        Check(
            "RunConfiguration fields and body",
            not wrong,
            "all fields and the body match" if not wrong else "differ: " + ", ".join(wrong),
        )
    ]


def _count(store: ReadableStore, query: str) -> int:
    rows = store.select(query)
    try:
        return int(rows[0]["n"])
    except (IndexError, KeyError, ValueError):
        return 0


def _one_value(rows: Sequence[Mapping[str, str]], key: str) -> str:
    if len(rows) != 1:
        return "none" if not rows else f"{len(rows)} rows"
    return rows[0].get(key, "")


def validate_metadata(
    label: str,
    runs: Sequence[RunInfo | WindowSource],
    hashes: Mapping[Path, str],
    config: RunConfig,
) -> MetadataProjection:
    """Build and SHACL-validate the metadata batch without a store."""
    projection = build_metadata(label, runs, hashes, config)
    gate.validate(gate.parse_batch(projection.data))
    return projection


def plan_metadata(store: GraphDB, projection: MetadataProjection) -> gate.IngestPlan:
    """Run the ingest gate's full plan for the meta graph."""
    return gate.plan(store, projection.data, projection.graph)


def plan_meta(store: GraphDB, projection: MetadataProjection) -> MetaPlan:
    """Plan the metadata graph and report the gate's status without writing."""
    try:
        plan = plan_metadata(store, projection)
    except gate.IngestRejected as exc:
        return MetaPlan(projection, "refused", rejected=str(exc))
    return MetaPlan(projection, plan.status.value, plan)


def write_metadata(store: GraphDB, plan: gate.IngestPlan) -> int:
    """Apply a metadata plan from :func:`plan_metadata`."""
    return gate.write(store, plan)
