"""Load one live day of the Veto Hierarchy system into the SYSTEM_LIVE graphs (Work item 47).

The live operator exports one folder per day and runs this command. The day is projected exactly
like one final run of one configuration/one window (``SYSTEM_LIVE``/``LIVE``) through
:func:`projection.load_veto.build_delivery`; this module adds what is live-specific:

* the ``manifest_live.json`` adapter and its folder/file/database/mask hash checks;
* the per-day replace: write three staging graphs, then one SPARQL Update with three exact
  ``MOVE <staging> TO <live>`` statements (one transaction), then verify counts and the mask;
* the target repository guard (never ``portfolio``) and the store-context check;
* the exit codes and the one JSON line that is always the last stdout line.

No projection logic is forked here. The live graphs are fixed and shared by every day:

* ``urn:graph:derived:backtest:live:LIVE:system_live``
* ``urn:graph:derived:backtest:selection:live:LIVE:system_live``
* ``urn:graph:derived:backtest:meta:live``
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rdflib

from etl import config
from kg_store import gate
from kg_store.graphdb import (
    PRODUCTION_REPOSITORY,
    GraphDB,
    GraphDBError,
    announce_target,
)
from projection.backtest import (
    ProjectionError,
    load_guard_catalog,
    universe_assets,
)
from projection.boundary import BoundaryError
from projection.control_counts import ControlCountError
from projection.delivery import ConfigError
from projection.live_manifest import (
    LIVE_LABEL,
    LiveManifestError,
    live_graph_names,
    read_live_manifest,
    staging_graph_names,
)
from projection.load_veto import (
    LoadVetoError,
    ShaclFailed,
    VetoGraph,
    _all_graphs,
    _existing,
    _shacl_context,
    build_delivery,
)
from projection.run_metadata import MetadataError
from projection.veto_events import DetailError
from projection.veto_manifest import VetoManifestError

DEFAULT_REPOSITORY = "portfolio_live"
DEFAULT_ASSETS_DB = Path("/workspaces/thesis/data/universe_history_gics.db")

#: The schema/context graphs the batch's SHACL validation reads from the target store.
REQUIRED_CONTEXT_GRAPHS: tuple[str, ...] = (
    "urn:graph:tbox",
    "urn:graph:reference",
    "urn:graph:rules:catalog",
)
UNIVERSE_PREFIX = "urn:graph:universe:"

#: The properties the final load forbids on a Tiingo-masked asset (Work item 45).
PRICE_PROPERTIES: tuple[str, ...] = (
    "alertValue",
    "alertThreshold",
    "stopDistancePct",
    "closePrice",
    "dailyReturn",
)
_LINK_PROPERTIES = ("guardAsset", "vetoOfAsset", "attractivenessOfAsset", "holdingAsset")
_SAFE_PART = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
_MASK_HEADER = ("asset_id", "ticker", "tiingo_price_rows", "first_date", "last_date")
_NS = rdflib.Namespace("https://thesis.local/kg/portfolio#")
_PREFIX = f"PREFIX : <{_NS}>\n"


class LiveError(RuntimeError):
    """A live loader step failed; ``exit_code`` is the contract's exit status."""

    exit_code = 2


class LiveStoreError(LiveError):
    """The target store is unreachable, refused, or lacks its schema/context."""

    exit_code = 4


class LiveWriteError(LiveError):
    """A write or post-swap verification failed; the message names the affected graphs."""

    exit_code = 5


class _UsageError(ValueError):
    """Bad command-line arguments; the JSON line still goes out."""


@dataclass
class Outcome:
    """What the final JSON line reports."""

    day: str | None
    repository: str = DEFAULT_REPOSITORY
    graphs: int = 0
    triples: int = 0
    shacl: str = "not_run"
    ok: bool = False
    error: str | None = None


def main(  # noqa: C901, PLR0911 -- one exit per failure class
    argv: Sequence[str] | None = None,
) -> int:
    """Run the loader; always print exactly one JSON object as the last stdout line."""
    outcome = Outcome(day=None)
    try:
        args = _parse_args(argv)
        outcome.day = args.day
        outcome.repository = args.repository
        _run(args, outcome)
    except _UsageError as exc:
        outcome.error = str(exc)
        return 2
    except SystemExit as exc:
        code = int(exc.code or 0)
        outcome.ok = code == 0
        outcome.error = None if code == 0 else f"exit {code}"
        return code
    except LiveWriteError as exc:
        outcome.error = str(exc)
        return 5
    except LiveStoreError as exc:
        outcome.error = str(exc)
        return 4
    except LiveError as exc:
        outcome.error = str(exc)
        return exc.exit_code
    except ShaclFailed as exc:
        outcome.shacl = "fails"
        outcome.error = str(exc)
        return 3
    except GraphDBError as exc:
        outcome.error = str(exc)
        return 4
    except (
        LiveManifestError,
        VetoManifestError,
        DetailError,
        LoadVetoError,
        ConfigError,
        MetadataError,
        BoundaryError,
        ProjectionError,
        ControlCountError,
        OSError,
    ) as exc:
        outcome.error = str(exc)
        return 2
    except Exception as exc:
        outcome.error = f"unexpected {type(exc).__name__}: {exc}"
        return 2
    else:
        return 0
    finally:
        _print_json(outcome)


def _run(args: argparse.Namespace, outcome: Outcome) -> None:
    if args.repository == PRODUCTION_REPOSITORY:
        raise LiveStoreError(
            f"refusing repository {PRODUCTION_REPOSITORY!r}: the live loader never writes to the "
            "final repository, whatever the environment says"
        )
    live = read_live_manifest(args.folder)
    if args.day != live.day:
        raise LiveError(f"--day {args.day} differs from the manifest day {live.day} in {live.path}")
    masked = _masked_tickers(live.price_mask.path)
    print(f"live day: {live.day} (formation {live.formation})")
    print(f"live run: {live.run_id}; book {live.book_code} id {live.book_id}")
    print(f"price mask: {len(masked)} asset(s)")

    manifest = live.veto_manifest()
    assets_db = args.assets_db or config.universe_db_path()
    result = build_delivery(
        manifest,
        LIVE_LABEL,
        assets_db=assets_db,
        validate_shacl=True,
        run_config=live.run_config(),
        require_control_counts=False,
        verified=live.hashes,
    )
    graphs = tuple(_all_graphs(result))
    _set_projection(outcome, graphs)
    outcome.shacl = "conforms"
    failures = _masked_batch_failures(graphs, masked)
    if failures:
        raise LiveError(
            "the Tiingo price mask forbids these projected values: " + "; ".join(failures)
        )

    if not args.write and not args.check_store:
        print("dry run complete: no store was contacted")
        outcome.ok = True
        return

    shacl_context = _shacl_context(
        universe_assets(assets_db), load_guard_catalog(config.schema_dir() / "rules.ttl")
    )[1]
    store = _open_store(args.repository)
    announce_target(store)
    _check_context(store)
    if args.check_store:
        _plan(store, graphs, shacl_context)
        print("pre-flight complete: nothing was written")
        outcome.ok = True
        return

    _write_day(store, graphs, masked, shacl_context)
    outcome.ok = True
    outcome.error = None


def _set_projection(outcome: Outcome, graphs: Sequence[VetoGraph]) -> None:
    outcome.graphs = len(graphs)
    outcome.triples = sum(graph.triples for graph in graphs)


def _open_store(repository: str) -> GraphDB:
    """Open the target repository with the environment's host/credentials only."""
    if repository == PRODUCTION_REPOSITORY:
        raise LiveStoreError(f"refusing repository {PRODUCTION_REPOSITORY!r}")
    os.environ.setdefault("KG_REPOSITORY", repository)
    try:
        base = GraphDB.from_env()
    except GraphDBError as exc:
        raise LiveStoreError(f"cannot open the target store: {exc}") from exc
    return dataclasses.replace(base, repository=repository)


def _check_context(store: GraphDB) -> None:
    """The repository must exist and hold the schema/universe graphs the batch points at."""
    try:
        sizes = store.explicit_graph_sizes()
    except GraphDBError as exc:
        raise LiveStoreError(f"cannot read repository {store.repository!r}: {exc}") from exc
    missing = [graph for graph in REQUIRED_CONTEXT_GRAPHS if sizes.get(graph, 0) == 0]
    if not any(graph.startswith(UNIVERSE_PREFIX) and count > 0 for graph, count in sizes.items()):
        missing.append(f"{UNIVERSE_PREFIX}*")
    if missing:
        raise LiveStoreError(
            f"repository {store.repository!r} is missing the schema/context graph(s): "
            + ", ".join(missing)
            + " (see docs/live-day-loader.md)"
        )


def _plan(store: GraphDB, graphs: Sequence[VetoGraph], shacl_context: rdflib.Graph) -> None:
    siblings = _parsed(graphs)
    for graph in graphs:
        if graph.triples == 0:
            print(f"pre-flight: {graph.graph}: empty, would replace with an empty graph")
            continue
        try:
            plan = gate.plan(
                store,
                graph.data,
                graph.graph,
                context=_context_with_sibling(shacl_context, siblings, graph),
                allow_existing=True,
                context_only=True,
            )
        except gate.IngestRejected as exc:
            raise LiveStoreError(f"{graph.graph}: store context refused the batch: {exc}") from exc
        except GraphDBError as exc:
            raise LiveStoreError(f"{graph.graph}: {exc}") from exc
        print(f"pre-flight: {graph.graph}: {plan.status.value}, {plan.triples} triples")


def _write_day(  # noqa: C901 -- one branch per pre-swap failure class
    store: GraphDB,
    graphs: Sequence[VetoGraph],
    masked: tuple[str, ...],
    shacl_context: rdflib.Graph,
) -> None:
    live = live_graph_names()
    staging = staging_graph_names()
    siblings = _parsed(graphs)
    try:
        for target in staging:
            _drop(store, target)
        for graph, target in zip(graphs, staging, strict=True):
            if graph.triples == 0:
                store.update(f"CREATE SILENT GRAPH <{target}>")
            else:
                plan = gate.plan(
                    store,
                    graph.data,
                    target,
                    context=_context_with_sibling(shacl_context, siblings, graph),
                    allow_existing=True,
                    context_only=True,
                )
                gate.write_batched(store, plan)
            count = _existing(store, target)
            if count != graph.triples:
                raise LiveStoreError(
                    f"staging {target}: stored {count}, projected {graph.triples}; "
                    "the previous day is untouched"
                )
    except (LiveError, KeyboardInterrupt):
        _cleanup(store, staging)
        raise
    except gate.IngestRejected as exc:
        _cleanup(store, staging)
        raise LiveStoreError(f"store context refused a staging graph: {exc}") from exc
    except GraphDBError as exc:
        _cleanup(store, staging)
        raise LiveStoreError(f"staging failed; the previous day is untouched: {exc}") from exc

    try:
        update = ";\n".join(
            f"MOVE <{source}> TO <{target}>" for source, target in zip(staging, live, strict=True)
        )
        store.update(update)
    except GraphDBError as exc:
        _cleanup(store, staging)
        raise LiveWriteError(
            "the swap failed after it began; affected SYSTEM_LIVE graphs: "
            + ", ".join(live)
            + f": {exc}"
        ) from exc

    try:
        failures = _verify_after_swap(store, graphs, masked)
    except GraphDBError as exc:
        raise LiveWriteError(
            "the post-swap verification failed; affected SYSTEM_LIVE graphs: "
            + ", ".join(live)
            + f": {exc}"
        ) from exc
    if failures:
        raise LiveWriteError(
            "verification after the swap failed; affected SYSTEM_LIVE graphs: "
            + ", ".join(live)
            + "\n"
            + "\n".join(f"  {line}" for line in failures)
        )
    print(f"write complete: {len(live)} graph(s) replaced, no repository deleted")


def _drop(store: GraphDB, graph: str) -> None:
    """Drop one exact graph IRI; never a wildcard, the default graph or a repository."""
    store.update(f"DROP SILENT GRAPH <{graph}>")


def _cleanup(store: GraphDB, staging: Sequence[str]) -> None:
    for graph in staging:
        try:
            _drop(store, graph)
        except GraphDBError:
            print(f"warning: could not drop staging graph {graph}", file=sys.stderr)


def _verify_after_swap(
    store: GraphDB, graphs: Sequence[VetoGraph], masked: tuple[str, ...]
) -> list[str]:
    failures: list[str] = []
    for graph in graphs:
        count = _existing(store, graph.graph)
        if count != graph.triples:
            failures.append(f"{graph.graph}: stored {count}, projected {graph.triples}")
    for staging in staging_graph_names():
        left = _existing(store, staging)
        if left:
            failures.append(f"{staging}: {left} triples left in staging")
    failures.extend(_masked_store_prices(store, masked))
    return failures


def _parsed(graphs: Sequence[VetoGraph]) -> dict[str, rdflib.Graph]:
    return {graph.graph: rdflib.Graph().parse(data=graph.data, format="turtle") for graph in graphs}


def _sibling(siblings: Mapping[str, rdflib.Graph], graph: VetoGraph) -> rdflib.Graph | None:
    if graph.kind == "m018":
        for name, parsed in siblings.items():
            if ":selection:" in name:
                return parsed
    if graph.kind == "selection":
        for name, parsed in siblings.items():
            if ":selection:" not in name and ":meta:" not in name:
                return parsed
    return None


def _context_with_sibling(
    shacl_context: rdflib.Graph, siblings: Mapping[str, rdflib.Graph], graph: VetoGraph
) -> rdflib.Graph:
    """The disk universe/rule context plus the batch's sibling graph, never written."""
    context = rdflib.Graph()
    for triple in shacl_context:
        context.add(triple)
    sibling = _sibling(siblings, graph)
    if sibling is not None:
        for triple in sibling:
            context.add(triple)
    return context


def _masked_tickers(path: Path) -> tuple[str, ...]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _MASK_HEADER:
                raise LiveError(f"{path}: expected header {', '.join(_MASK_HEADER)}")
            tickers: list[str] = []
            for number, row in enumerate(reader, 2):
                ticker = (row.get("ticker") or "").strip()
                if not ticker:
                    raise LiveError(f"{path}:{number}: empty ticker")
                if not _SAFE_PART.fullmatch(ticker):
                    raise LiveError(f"{path}:{number}: ticker {ticker!r} cannot form an IRI")
                tickers.append(ticker)
    except OSError as exc:
        raise LiveError(f"{path}: {exc}") from exc
    if not tickers:
        raise LiveError(f"{path}: the price mask is empty")
    return tuple(tickers)


def _masked_batch_failures(graphs: Sequence[VetoGraph], masked: tuple[str, ...]) -> list[str]:
    failures: list[str] = []
    for graph in graphs:
        parsed = rdflib.Graph().parse(data=graph.data, format="turtle")
        failures.extend(_masked_graph_failures(parsed, masked, graph.graph))
    return failures


def _masked_graph_failures(graph: rdflib.Graph, masked: tuple[str, ...], where: str) -> list[str]:
    failures: list[str] = []
    for ticker in masked:
        asset = _NS[ticker]
        for prop in PRICE_PROPERTIES:
            if (asset, _NS[prop], None) in graph:
                failures.append(f"{where}: {ticker} carries :{prop}")
        for link in _LINK_PROPERTIES:
            for subject in graph.subjects(_NS[link], asset):
                for prop in PRICE_PROPERTIES:
                    if (subject, _NS[prop], None) in graph:
                        failures.append(
                            f"{where}: {subject.n3()} linked to masked {ticker} carries :{prop}"
                        )
    return failures


def _masked_store_prices(store: GraphDB, masked: tuple[str, ...]) -> list[str]:
    values = " ".join(f"<{_NS[ticker]}>" for ticker in masked)
    links = "|".join(f":{link}" for link in _LINK_PROPERTIES)
    prices = ", ".join(f":{prop}" for prop in PRICE_PROPERTIES)
    failures: list[str] = []
    for graph in live_graph_names():
        rows = store.select(
            _PREFIX
            + f"SELECT DISTINCT ?s ?p WHERE {{ GRAPH <{graph}> {{ "
            + f"{{ VALUES ?s {{ {values} }} ?s ?p ?v }} UNION "
            + f"{{ ?s ({links}) ?a . VALUES ?a {{ {values} }} ?s ?p ?v }} "
            + f"FILTER (?p IN ({prices})) }} }}"
        )
        failures.extend(f"{graph}: {row.get('s')} carries {row.get('p')}" for row in rows)
    return failures


def _print_json(outcome: Outcome) -> None:
    payload: dict[str, Any] = {
        "day": outcome.day,
        "repository": outcome.repository,
        "graphs": outcome.graphs,
        "triples": outcome.triples,
        "shacl": outcome.shacl,
        "ok": outcome.ok,
    }
    if not outcome.ok:
        payload["error"] = outcome.error or "unknown error"
    print(json.dumps(payload, ensure_ascii=False))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--folder", required=True, type=Path, help="the day's graph_export folder")
    parser.add_argument("--day", required=True, help="the day to load (YYYY-MM-DD)")
    parser.add_argument(
        "--repository",
        default=DEFAULT_REPOSITORY,
        help=f"target repository (default: {DEFAULT_REPOSITORY}; never {PRODUCTION_REPOSITORY})",
    )
    parser.add_argument(
        "--assets-db",
        type=Path,
        default=None,
        help=(
            "universe database for SHACL context "
            "(default: SQL_UNIVERSE_DB, then the bundled default when present)"
        ),
    )
    parser.add_argument("--check-store", action="store_true", help="read-only store pre-flight")
    parser.add_argument(
        "--write", action="store_true", help="stage and swap the SYSTEM_LIVE graphs"
    )
    args = parser.parse_args(argv)
    if args.check_store and args.write:
        raise _UsageError("--check-store only reads; do not combine it with --write")
    if not args.repository:
        raise _UsageError("--repository must not be empty")
    try:
        parsed = datetime.date.fromisoformat(args.day)
    except ValueError:
        raise _UsageError(f"--day {args.day!r} is not a YYYY-MM-DD date") from None
    args.day = parsed.isoformat()
    if args.assets_db is None:
        if os.environ.get("SQL_UNIVERSE_DB"):
            args.assets_db = config.universe_db_path()
        elif DEFAULT_ASSETS_DB.is_file():
            args.assets_db = DEFAULT_ASSETS_DB
    return args


class _Parser(argparse.ArgumentParser):
    """An argument parser that never exits before the loader prints its JSON line."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """The public argument parser (tests and ``cli/load_live.py``)."""
    return _parse_args(argv)
