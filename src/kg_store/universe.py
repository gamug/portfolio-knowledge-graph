"""Load the asset master (``:Universe``, ``:Asset``, ``:UniverseMembership``) into the store.

``portfolio-data-mining``'s point-in-time ``universe.db`` is the asset master (D1, T-100):
:mod:`etl.asset_master` already turns it into one ``:Asset`` per company line (a pure ticker
succession folds into one, named by the latest symbol) or per symbol (concurrent classes, a mixed
CIK, a CIK-less stint) and one ``:UniverseMembership`` per stint in the single ``:SP500Index``
``:Universe``. That module writes flat Turtle for ``cli/build_data_ttl.py``; this one puts the same
individuals into a GraphDB named graph **through the ingest gate**, so a backtest or a score batch
that links ``:Asset`` nodes finds them in the store instead of being refused (T-220, T-264).

    uv run python cli/load_universe.py                  # dry run: read, build, SHACL-validate
    uv run python cli/load_universe.py --write          # append through the gate

**The graph is the quarter graph, not ``urn:graph:reference``.** ``docs/07`` assigns the universe
ABox to ``urn:graph:universe:{year}-Q{n}``, computed here from ``--as-of`` (the day the run sees the
catalog). ``urn:graph:reference`` holds ``schema/reference.ttl``, which ``cli/load_schema.py``
drops and rewrites as a whole on every schema reload: ABox individuals written there would vanish
on the next reload, and the loader could not append to it. The quarter graph is append-only and
gate-accepted, and the catalog is the membership boundary of that quarter. ``reference.ttl`` keeps
its five worked-example assets: the loader reads their tickers and emits only their memberships,
so those ``:Asset`` individuals are neither re-declared nor changed (a second declaration would
clash with ``cikNumber``'s functional-property contract, as in the ETL).

``--since`` keeps the stints that were still open on or after that date (``valid_to`` absent, or
``valid_to >= since``; ``validTo`` is inclusive, its last day of membership); the default
``2019-01-02`` drops a ticker's earlier company when upstream reused the symbol (``CEG``,
``DELL``, ``Q``), so the resolved ``:Asset`` describes the company the backtest windows and the
live index contain. The dropped stints are counted, never silently omitted. A ticker whose kept
stints would belong to two different CIKs stops the run with both CIKs named, rather than silently
picking one (T-265).

A dry run (the default) contacts no store: it reads ``universe.db``, builds the batch and runs the
gate's store-free checks plus ``shapes.ttl`` with the local ``schema/reference.ttl`` standing in
for what a loaded store would hold about the industries and the five worked-example assets.
``--write`` appends the batch through :func:`kg_store.gate.ingest`, which re-validates it against
the store's own copy of those individuals, and writing the production repository
(``KG_REPOSITORY=portfolio``) also needs ``--to-production``, as ``cli/project_backtest.py`` does.

The load is append-only, as ``docs/07`` requires. Once a quarter's graph exists the gate refuses a
second load; a load into a later quarter re-declares the same ``:Asset``/``:Universe`` individuals
and the gate's check 6 refuses those, so this is a one-time catalog load per repository (a new
automation gets its own repository, Work item 17). A later quarter's *changed* memberships are a
different batch: only their new individuals, not the catalog again.

``--delta`` (Work item 28) is that batch. It reads the source with the same ``--since`` and
``resolve_assets`` and the store with ``SELECT`` only, then renders four categories: new assets,
new memberships of stored assets, ``:validTo`` closures of stored open memberships, and **drift**
(reported, never applied: the store is append-only). New values go into the next
``urn:graph:universe:{year}-Q{n}:delta:{n}`` graph through the same gate; the base quarter graph is
never touched. With no actionable delta the run prints an empty delta and writes nothing, so a run
immediately after a write is idempotent.
"""

from __future__ import annotations

import argparse
import datetime
import io
import re
import sqlite3
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import rdflib
from rdflib.namespace import RDF, RDFS, XSD

from etl import asset_master, config
from etl.build_data_ttl import reference_asset_tickers
from etl.common import gics_rollup
from kg_store import gate
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError, schema_dir

#: Stints closed before this date are dropped by default: a ticker reused by another company
#: (``CEG``, ``DELL``, ``Q``) keeps only the era the backtests and the live index can see.
DEFAULT_SINCE = "2019-01-02"

_PREFIXES = (
    "@prefix :      <https://thesis.local/kg/portfolio#> .\n"
    "@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .\n"
    "@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .\n\n"
)

#: The portfolio namespace and the explicit-statements virtual graph (no inferred statements).
KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")
_EXPLICIT = "http://www.ontotext.com/explicit"

#: The stored catalog, read by :func:`read_store` with SELECT only.
_ASSET_STATE_QUERY = (
    f"SELECT ?s ?p ?o FROM <{_EXPLICIT}> WHERE {{ "  # noqa: S608 - fixed IRIs, no user input
    f"?s a <{KG.Asset}> . VALUES ?p {{ "
    f"<{KG.tickerSymbol}> <{KG.companyName}> <{KG.cikNumber}> <{KG.classifiedAs}> "
    f"}} ?s ?p ?o }}"
)
_MEMBERSHIP_STATE_QUERY = (
    f"SELECT ?m ?asset ?from ?to FROM <{_EXPLICIT}> WHERE {{ "  # noqa: S608 - fixed IRIs
    f"?m a <{KG.UniverseMembership}> ; <{KG.membershipUniverse}> <{KG.SP500Index}> ; "
    f"<{KG.membershipAsset}> ?asset ; <{KG.validFrom}> ?from . "
    f"OPTIONAL {{ ?m <{KG.validTo}> ?to }} }}"
)


@dataclass(frozen=True)
class UniverseBatch:
    """One quarter's asset-master batch and the numbers the run reports."""

    graph: str
    as_of: str
    since: str
    data: bytes
    triples: int
    summary: asset_master.UniverseSummary
    warnings: tuple[str, ...]
    kept: tuple[asset_master.Stint, ...]
    dropped: tuple[asset_master.Stint, ...]
    already_defined: frozenset[str]
    cik_less_open: tuple[str, ...]


@dataclass(frozen=True)
class StoredAsset:
    """One stored ``:Asset`` and the values the delta compares with the source."""

    iri: str
    ticker: str | None
    company_name: str | None
    cik: str | None
    classified_as: str | None


@dataclass(frozen=True)
class StoredMembership:
    """One stored ``:UniverseMembership`` of ``:SP500Index`` (``valid_to`` None while open)."""

    iri: str
    asset: str
    valid_from: str
    valid_to: str | None


@dataclass(frozen=True)
class StoreState:
    """What the store holds for the catalog: assets and ``:SP500Index`` memberships."""

    assets: Mapping[str, StoredAsset]
    memberships: Mapping[str, StoredMembership]


@dataclass(frozen=True)
class _Delta:
    """The classification before it is rendered: membership -> the asset it links to."""

    new_assets: tuple[str, ...]
    new_memberships: tuple[tuple[str, str], ...]
    closures: tuple[tuple[str, str], ...]
    drift: tuple[str, ...]


@dataclass(frozen=True)
class DeltaBatch:
    """The batch ``--delta`` would write, the four category counts and the target graph."""

    graph: str
    as_of: str
    since: str
    data: bytes
    triples: int
    summary: asset_master.UniverseSummary
    warnings: tuple[str, ...]
    kept: tuple[asset_master.Stint, ...]
    dropped: tuple[asset_master.Stint, ...]
    new_assets: tuple[str, ...]
    new_memberships: tuple[str, ...]
    closures: tuple[tuple[str, str], ...]
    drift: tuple[str, ...]
    source_assets: int
    source_memberships: int
    stored_assets: int
    stored_memberships: int

    @property
    def actionable(self) -> bool:
        """Whether there is anything to write (drift alone is never written)."""
        return bool(self.new_assets or self.new_memberships or self.closures)


class UniverseDeltaError(ValueError):
    """The store cannot take a delta (no catalog, or a reference asset is missing)."""


def _full(local: str) -> str:
    """Expand a ``:local`` name to its full IRI; leave an absolute IRI alone."""
    return local if local.startswith(("http://", "https://")) else str(KG[local.lstrip(":")])


def _short(iri: str | None) -> str:
    """A full IRI as ``:local`` when it is in the portfolio namespace."""
    if iri is None:
        return "none"
    text = str(iri)
    return ":" + text[len(str(KG)) :] if text.startswith(str(KG)) else text


def today() -> str:
    """Today in UTC: the default ``--as-of``."""
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def iso_date(text: str) -> str:
    """``--since``/``--as-of``: a ``YYYY-MM-DD`` date, refused here rather than at the gate."""
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a YYYY-MM-DD date") from None


def quarter(as_of: str) -> str:
    """The calendar quarter of an ISO date, ``YYYY-Qn`` (the gate's accepted universe name)."""
    day = datetime.date.fromisoformat(as_of)
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


def graph_name(as_of: str) -> str:
    """The append-only universe graph for ``--as-of`` (``docs/07``)."""
    return f"urn:graph:universe:{quarter(as_of)}"


def keep_stints(stints: Sequence[asset_master.Stint], since: str) -> list[asset_master.Stint]:
    """The stints still open on or after ``since`` (``validTo`` is inclusive)."""
    return [s for s in stints if s.valid_to is None or s.valid_to >= since]


def cik_less_open(stints: Sequence[asset_master.Stint]) -> list[str]:
    """Assets with no CIK that keep an open membership.

    ``build_assets`` describes a resolved ``:Asset`` with its latest stint, so a missing CIK there
    and an open stint anywhere is exactly what ``AssetShape``'s CIK-or-closed rule refuses. The
    resolution is the loader's own (a CIK succession folds into one asset), not a second grouping.
    """
    return sorted(
        asset.symbol
        for asset in asset_master.resolve_assets(list(stints))
        if any(stint.valid_to is None for stint in asset.stints) and not asset.cik
    )


def render(
    stints: list[asset_master.Stint],
    already_defined: set[str],
    since: str,
    as_of: str,
    warnings: list[str],
) -> tuple[bytes, asset_master.UniverseSummary]:
    """Build the Turtle batch for ``stints``; no store and no validation."""
    out = io.StringIO()
    out.write(_PREFIXES)
    out.write(
        f"# Asset master for {quarter(as_of)} (as of {as_of}), generated by "
        f"cli/load_universe.py from universe.db.\n"
        f"# Stints kept: valid_to absent or >= {since}.\n\n"
    )
    summary = asset_master.build_assets(stints, out, warnings, already_defined)
    return out.getvalue().encode("utf-8"), summary


def plan(
    db_path: str | Path, since: str = DEFAULT_SINCE, as_of: str | None = None
) -> UniverseBatch:
    """Read ``universe.db`` and build the batch for the quarter graph of ``as_of``."""
    as_of = as_of or today()
    path = Path(db_path)
    warnings: list[str] = []
    stints = asset_master.read_stints(path, warnings)
    kept = keep_stints(stints, since)
    dropped = [s for s in stints if s not in kept]
    already_defined = reference_asset_tickers()
    data, summary = render(kept, already_defined, since, as_of, warnings)
    summary = replace(summary, file_mtime=path.stat().st_mtime)
    return UniverseBatch(
        graph=graph_name(as_of),
        as_of=as_of,
        since=since,
        data=data,
        triples=len(gate.parse_batch(data)),
        summary=summary,
        warnings=tuple(warnings),
        kept=tuple(kept),
        dropped=tuple(dropped),
        already_defined=frozenset(already_defined),
        cik_less_open=tuple(cik_less_open(kept)),
    )


def read_store(store: GraphDB) -> StoreState:
    """Read the stored catalog with SELECT only: assets and ``:SP500Index`` memberships."""
    values: dict[str, dict[str, set[str]]] = {}
    for row in store.select(_ASSET_STATE_QUERY):
        subject, predicate, obj = row.get("s"), row.get("p"), row.get("o")
        if subject is None or predicate is None or obj is None:
            continue
        values.setdefault(subject, {}).setdefault(predicate, set()).add(obj)

    def first(properties: dict[str, set[str]], predicate: rdflib.URIRef) -> str | None:
        held = properties.get(str(predicate))
        return min(held) if held else None

    assets = {
        subject: StoredAsset(
            iri=subject,
            ticker=first(properties, KG.tickerSymbol),
            company_name=first(properties, KG.companyName),
            cik=first(properties, KG.cikNumber),
            classified_as=first(properties, KG.classifiedAs),
        )
        for subject, properties in sorted(values.items())
    }
    memberships: dict[str, StoredMembership] = {}
    for row in store.select(_MEMBERSHIP_STATE_QUERY):
        membership, asset, valid_from = row.get("m"), row.get("asset"), row.get("from")
        if membership is None or asset is None or valid_from is None:
            continue
        memberships[membership] = StoredMembership(
            iri=membership,
            asset=asset,
            valid_from=valid_from,
            valid_to=row.get("to"),
        )
    return StoreState(assets=assets, memberships=memberships)


def delta_graph_name(as_of: str, store: GraphDB) -> str:
    """The next free ``urn:graph:universe:{quarter}:delta:{n}`` for ``as_of``."""
    prefix = f"urn:graph:universe:{quarter(as_of)}:delta:"
    query = (
        f"SELECT DISTINCT ?g FROM <{_EXPLICIT}> WHERE {{ "  # noqa: S608 - fixed prefix
        f'GRAPH ?g {{ ?s ?p ?o }} FILTER(STRSTARTS(STR(?g), "{prefix}")) }}'
    )
    rows = store.select(query)
    used = {
        int(match.group(1))
        for row in rows
        if (match := re.fullmatch(re.escape(prefix) + r"([1-9][0-9]*)", row.get("g", "")))
    }
    return f"{prefix}{max(used, default=0) + 1}"


def _industry_local(stint: asset_master.Stint) -> str | None:
    """The ``:Ind_*`` the loader would write for a stint's sub-industry, if any."""
    if not stint.sub_industry:
        return None
    return gics_rollup.lookup(stint.sub_industry)


def _compare_asset(
    asset: asset_master.ResolvedAsset, stored: StoredAsset, drift: list[str]
) -> None:
    """Report every stored ``:Asset`` value that differs from the source's latest stint."""
    latest = asset.latest
    industry = _industry_local(latest)
    expected_classified = _full(f":{industry}") if industry else None
    iris = _short(stored.iri)
    if stored.ticker != latest.symbol:
        drift.append(
            f"asset {iris}: tickerSymbol differs (stored {stored.ticker!r}, source {latest.symbol!r})"
        )
    if stored.company_name != latest.security:
        drift.append(
            f"asset {iris}: companyName differs "
            f"(stored {stored.company_name!r}, source {latest.security!r})"
        )
    if stored.cik != latest.cik:
        drift.append(
            f"asset {iris}: cikNumber differs (stored {stored.cik!r}, source {latest.cik!r})"
        )
    if stored.classified_as != expected_classified:
        drift.append(
            f"asset {iris}: classifiedAs differs "
            f"(stored {_short(stored.classified_as)}, source {_short(expected_classified)})"
        )


def _compare_membership(  # noqa: PLR0913 -- the stored/source pair is the point
    membership: str,
    asset_iri: str,
    stint: asset_master.Stint,
    stored: StoredMembership,
    *,
    closures: list[tuple[str, str]],
    drift: list[str],
) -> None:
    """Report a stored membership that differs; a still-open one may become a closure."""
    name = _short(membership)
    if stored.asset != asset_iri:
        drift.append(
            f"membership {name}: membershipAsset differs "
            f"(stored {_short(stored.asset)}, source {_short(asset_iri)})"
        )
        return
    if stored.valid_from != stint.valid_from:
        drift.append(
            f"membership {name}: validFrom differs "
            f"(stored {stored.valid_from!r}, source {stint.valid_from!r})"
        )
        return
    if stored.valid_to == stint.valid_to:
        return
    if stored.valid_to is None and stint.valid_to is not None:
        closures.append((membership, stint.valid_to))
        return
    if stored.valid_to is not None and stint.valid_to is None:
        drift.append(
            f"membership {name}: validTo differs (stored closed {stored.valid_to!r}, source open)"
        )
        return
    drift.append(
        f"membership {name}: validTo differs "
        f"(stored {stored.valid_to!r}, source {stint.valid_to!r})"
    )


def _classify(
    source_assets: Sequence[asset_master.ResolvedAsset],
    store: StoreState,
    already_defined: set[str],
) -> _Delta:
    """Split the source/store difference into new assets, new memberships, closures and drift."""
    new_assets: list[str] = []
    new_memberships: dict[str, str] = {}
    closures: list[tuple[str, str]] = []
    drift: list[str] = []
    source_asset_iris: set[str] = set()
    source_membership_iris: set[str] = set()

    for asset in source_assets:
        asset_iri = _full(f":{asset.symbol}")
        source_asset_iris.add(asset_iri)
        stored_asset = store.assets.get(asset_iri)
        if stored_asset is None:
            if asset.symbol not in already_defined:
                new_assets.append(asset.symbol)
        elif asset.symbol not in already_defined:
            # reference.ttl owns its five assets' values: the loader never writes or compares them.
            _compare_asset(asset, stored_asset, drift)

        for stint in asset.stints:
            membership = _full(asset_master.membership_iri(stint))
            source_membership_iris.add(membership)
            stored_membership = store.memberships.get(membership)
            if stored_membership is None:
                new_memberships[membership] = asset_iri
            elif stored_asset is None:
                drift.append(
                    f"membership {_short(membership)}: the asset {_short(asset_iri)} is new but "
                    f"the membership is already stored under {_short(stored_membership.asset)}"
                )
            else:
                _compare_membership(
                    membership,
                    asset_iri,
                    stint,
                    stored_membership,
                    closures=closures,
                    drift=drift,
                )

    reference_iris = {_full(f":{ticker}") for ticker in already_defined}
    for iri in sorted(set(store.assets) - source_asset_iris - reference_iris):
        drift.append(f"asset {_short(iri)}: stored but absent from the source")
    for iri in sorted(set(store.memberships) - source_membership_iris):
        drift.append(f"membership {_short(iri)}: stored but absent from the source")
    return _Delta(
        new_assets=tuple(new_assets),
        new_memberships=tuple(new_memberships.items()),
        closures=tuple(closures),
        drift=tuple(sorted(drift)),
    )


def _serialize_sorted(graph: rdflib.Graph) -> bytes:
    """Deterministic Turtle: one triple per line, sorted, with the prefixes the batch uses."""
    manager = graph.namespace_manager
    lines = [
        f"@prefix : <{KG}> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]
    for subject, predicate, obj in sorted(graph, key=lambda t: tuple(map(str, t))):
        lines.append(f"{subject.n3(manager)} {predicate.n3(manager)} {obj.n3(manager)} .")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _render_delta(  # noqa: PLR0913 -- the render context is explicit at the call site
    kept: list[asset_master.Stint],
    already_defined: set[str],
    since: str,
    as_of: str,
    *,
    warnings: list[str],
    delta: _Delta,
) -> tuple[bytes, int, asset_master.UniverseSummary]:
    """Render only the selected asset blocks, membership blocks, links and closures."""
    full_data, summary = render(kept, already_defined, since, as_of, warnings)
    if not delta.new_assets and not delta.new_memberships and not delta.closures:
        return b"", 0, summary

    full = gate.parse_batch(full_data)
    new_asset_iris = {_full(f":{symbol}") for symbol in delta.new_assets}
    links = dict(delta.new_memberships)
    new_membership_iris = set(links)
    out = rdflib.Graph()
    out.namespace_manager.bind("", KG, replace=True)
    out.namespace_manager.bind("rdf", RDF, replace=True)
    out.namespace_manager.bind("rdfs", RDFS, replace=True)
    out.namespace_manager.bind("xsd", XSD, replace=True)
    for subject, predicate, obj in full:
        subject_iri = str(subject)
        if subject_iri in new_asset_iris:
            if predicate == KG.hasUniverseMembership and str(obj) not in new_membership_iris:
                continue
            out.add((subject, predicate, obj))
        elif subject_iri in new_membership_iris:
            out.add((subject, predicate, obj))
    for membership, asset_iri in links.items():
        out.add((rdflib.URIRef(asset_iri), KG.hasUniverseMembership, rdflib.URIRef(membership)))
    for membership, valid_to in delta.closures:
        out.add(
            (rdflib.URIRef(membership), KG.validTo, rdflib.Literal(valid_to, datatype=XSD.date))
        )
    return _serialize_sorted(out), len(out), summary


def plan_delta(
    db_path: str | Path,
    store: GraphDB,
    since: str = DEFAULT_SINCE,
    as_of: str | None = None,
) -> DeltaBatch:
    """Read the source and the store, classify the delta and render its batch (read-only)."""
    as_of = as_of or today()
    path = Path(db_path)
    warnings: list[str] = []
    stints = asset_master.read_stints(path, warnings)
    kept = keep_stints(stints, since)
    dropped = [s for s in stints if s not in kept]
    already_defined = reference_asset_tickers()
    state = read_store(store)

    missing = sorted(
        ticker for ticker in already_defined if _full(f":{ticker}") not in state.assets
    )
    if missing:
        raise UniverseDeltaError(
            "the store does not hold reference.ttl's :Asset individual(s) "
            + ", ".join(f":{ticker}" for ticker in missing)
            + "; load the schema there before a delta"
        )
    if not state.memberships:
        raise UniverseDeltaError(
            "the store holds no :SP500Index :UniverseMembership catalog; load the full catalog "
            "with cli/load_universe.py (without --delta) first"
        )

    source_assets = asset_master.resolve_assets(kept)
    delta = _classify(source_assets, state, already_defined)
    data, triples, summary = _render_delta(
        kept, already_defined, since, as_of, warnings=warnings, delta=delta
    )
    summary = replace(summary, file_mtime=path.stat().st_mtime)
    return DeltaBatch(
        graph=delta_graph_name(as_of, store),
        as_of=as_of,
        since=since,
        data=data,
        triples=triples,
        summary=summary,
        warnings=tuple(warnings),
        kept=tuple(kept),
        dropped=tuple(dropped),
        new_assets=delta.new_assets,
        new_memberships=tuple(membership for membership, _ in delta.new_memberships),
        closures=delta.closures,
        drift=delta.drift,
        source_assets=len(source_assets),
        source_memberships=len(kept),
        stored_assets=len(state.assets),
        stored_memberships=len(state.memberships),
    )


def check_delta(
    batch: DeltaBatch, store: GraphDB, directory: Path | None = None
) -> gate.IngestPlan | None:
    """Run the real gate plan for the actionable delta; read-only, ``None`` for an empty delta.

    This is every store-dependent check the write runs: the target graph's existence (check 2),
    the typed individuals already stored (check 6) and the closing state (check 7), after the
    same shape validation. It returns the plan so the caller can report its status.
    """
    if not batch.actionable:
        return None
    return gate.plan(store, batch.data, batch.graph, directory)


def write_delta(batch: DeltaBatch, store: GraphDB, directory: Path | None = None) -> int:
    """Plan and append the actionable delta through the gate; an empty delta writes nothing."""
    if not batch.actionable:
        return 0
    return gate.write(store, gate.plan(store, batch.data, batch.graph, directory))


def report_delta(batch: DeltaBatch, db_path: Path) -> list[str]:
    """The end-of-run delta summary: the four categories, the drift list and the target graph."""
    lines = [
        f"universe.db: {db_path}",
        f"  {batch.summary.freshness_line()}",
        f"--since {batch.since} (as of {batch.as_of}): source {batch.source_assets} asset(s), "
        f"{batch.source_memberships} membership(s); store {batch.stored_assets} asset(s), "
        f"{batch.stored_memberships} membership(s)",
        f"delta: {len(batch.new_assets)} new asset(s), {len(batch.new_memberships)} new "
        f"membership(s), {len(batch.closures)} closure(s), {len(batch.drift)} drift item(s)",
        f"target graph: {batch.graph}",
    ]
    if batch.new_assets:
        lines.append("new assets: " + ", ".join(f":{symbol}" for symbol in batch.new_assets))
    if batch.new_memberships:
        lines.append("new memberships: " + ", ".join(map(_short, batch.new_memberships)))
    if batch.closures:
        lines.append(
            "closures: "
            + ", ".join(
                f"{_short(membership)} validTo {date}" for membership, date in batch.closures
            )
        )
    if batch.drift:
        lines.append(f"drift ({len(batch.drift)}) -- reported, never applied:")
        lines.extend(f"  - {line}" for line in batch.drift)
    else:
        lines.append("drift (0)")
    if not batch.actionable:
        lines.append("empty delta: nothing to write")
    return lines


def reference_context(refs: set[rdflib.URIRef], directory: Path) -> rdflib.Graph:
    """What ``schema/reference.ttl`` says about the individuals a dry-run batch points at.

    A loaded store holds the same triples in ``urn:graph:reference``; only their subjects are
    needed, since a reference is read for its type and the shape paths on it.
    """
    reference = rdflib.Graph().parse(directory / "reference.ttl", format="turtle")
    context = rdflib.Graph()
    for subject, predicate, obj in reference:
        if subject in refs:
            context.add((subject, predicate, obj))
    return context


def check(batch: UniverseBatch, directory: Path | None = None) -> None:
    """Dry-run validation: the gate's checks and ``shapes.ttl``, no store.

    Raises :class:`kg_store.gate.IngestRejected` (or ``ShaclRejected``) when the batch is refused.
    """
    directory = (directory or schema_dir()).resolve()
    data = gate.parse_batch(batch.data)
    schema = gate.load_gate_schema(directory)
    refs = gate.references(data, schema)
    gate.validate(data, directory, reference_context(refs, directory))


def write(batch: UniverseBatch, store: GraphDB, directory: Path | None = None) -> int:
    """Append the batch through the gate; returns the triples written."""
    return gate.ingest(store, batch.data, batch.graph, directory)


def _symbols(stints: Sequence[asset_master.Stint]) -> set[str]:
    return {s.symbol for s in stints}


def report(batch: UniverseBatch, db_path: Path) -> list[str]:
    """The end-of-run summary: what ``--since`` kept and dropped, and what was built."""
    all_stints = [*batch.kept, *batch.dropped]
    kept_symbols, dropped_symbols = _symbols(batch.kept), _symbols(batch.dropped)
    gone, later = dropped_symbols - kept_symbols, dropped_symbols & kept_symbols
    reused = len(batch.already_defined & kept_symbols)
    lines = [
        f"universe.db: {db_path}",
        f"  {batch.summary.freshness_line()}",
        f"--since {batch.since} (as of {batch.as_of}): kept {len(batch.kept)} of "
        f"{len(all_stints)} stint(s) over {len(kept_symbols)} symbol(s); dropped "
        f"{len(batch.dropped)} stint(s) over {len(dropped_symbols)} symbol(s) "
        f"({len(gone)} symbol(s) not loaded at all, {len(later)} with a later stint kept)",
        f"Assets: {batch.summary.assets_written} written"
        + (f", {reused} already in reference.ttl" if reused else "")
        + f" ({len(kept_symbols)} symbol(s) -> {len(batch.summary.tickers)} asset(s))",
        f"Memberships: {batch.summary.memberships} "
        f"({batch.summary.open_memberships} open, {batch.summary.closed_memberships} closed)",
        f"target graph: {batch.graph}",
        f"triples: {batch.triples}",
    ]
    if batch.cik_less_open:
        lines.append(
            f"CIK-less with an open membership ({len(batch.cik_less_open)}): "
            + ", ".join(batch.cik_less_open)
            + " -- AssetShape refuses these"
        )
    return lines


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--since",
        type=iso_date,
        default=DEFAULT_SINCE,
        metavar="YYYY-MM-DD",
        help=f"keep stints open on or after this date (default: {DEFAULT_SINCE})",
    )
    parser.add_argument(
        "--as-of",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="the day the catalog is seen as of; names the quarter graph (default: today in UTC)",
    )
    parser.add_argument(
        "--delta",
        action="store_true",
        help="read the stored catalog and write only the incremental changes (Work item 28)",
    )
    parser.add_argument("--write", action="store_true", help="append the batch to the store")
    parser.add_argument(
        "--to-production",
        action="store_true",
        help="with --write: allow the production repository (a maintainer decision)",
    )
    args = parser.parse_args(argv)
    if args.to_production and not args.write:
        parser.error("--to-production only matters with --write")
    return args


def _production_guard(store: GraphDB) -> None:
    """Refuse a production write without the explicit maintainer opt-in."""
    if store.repository == PRODUCTION_REPOSITORY:
        print(
            "--write to the production repository needs --to-production: the asset master is a "
            "catalog every later graph links to, so loading it is the maintainer's decision",
            file=sys.stderr,
        )
        raise SystemExit(2)


def open_store(args: argparse.Namespace) -> GraphDB | None:
    """The store a ``--write`` appends to; ``--delta`` always opens it read-only to diff."""
    if args.delta:
        store = GraphDB.from_env()
        if args.write and not args.to_production:
            _production_guard(store)
        return store
    if not args.write:
        return None
    store = GraphDB.from_env()
    if not args.to_production:
        _production_guard(store)
    return store


def _run_full(args: argparse.Namespace, db_path: Path, store: GraphDB | None) -> None:
    """The full-load branch (the default): report, validate dry-run or write the catalog."""
    batch = plan(db_path, args.since, args.as_of)
    for line in report(batch, db_path):
        print(line)
    if batch.warnings:
        print(f"{len(batch.warnings)} warning(s):")
        for warning in batch.warnings:
            print(f"  - {warning}")
    if store is None:
        check(batch)
        print("SHACL: conforms (gate.validate; dry run, nothing written)")
    else:
        written = write(batch, store)
        print(f"written: {written} triples to {batch.graph}")


def _run_delta(args: argparse.Namespace, db_path: Path, store: GraphDB) -> None:
    """The ``--delta`` branch: report, validate dry-run or write the actionable batch."""
    delta = plan_delta(db_path, store, args.since, args.as_of)
    for line in report_delta(delta, db_path):
        print(line)
    if delta.warnings:
        print(f"{len(delta.warnings)} warning(s):")
        for warning in delta.warnings:
            print(f"  - {warning}")
    if not delta.actionable:
        print("done: empty delta, nothing written")
    elif not args.write:
        plan = check_delta(delta, store)
        assert plan is not None  # only an actionable delta reaches this branch
        if plan.status is gate.IngestPlanStatus.ALREADY_IN_STORE:
            print(
                f"pre-flight: already-in-the-store (skipped): {plan.graph} (dry run, nothing written)"
            )
        else:
            print(f"pre-flight: {plan.status.value}: {plan.graph} (dry run, nothing written)")
    else:
        written = write_delta(delta, store)
        print(f"written: {written} triples to {delta.graph}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = config.universe_db_path()
    started = time.time()
    try:
        store = open_store(args)
        if args.delta:
            assert store is not None  # --delta always opens it, even for the dry run
            _run_delta(args, db_path, store)
        else:
            _run_full(args, db_path, store)
    except (asset_master.AssetResolutionError, UniverseDeltaError) as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 1
    except gate.IngestRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:  # a missing database, or one without universe_membership
        print(f"source error: {exc} (SQL_UNIVERSE_DB)", file=sys.stderr)
        return 1
    except GraphDBError as exc:
        print(f"store error: {exc}", file=sys.stderr)
        return 1
    except (OSError, SyntaxError) as exc:
        print(f"file error: {exc}", file=sys.stderr)
        return 1
    print(f"done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
