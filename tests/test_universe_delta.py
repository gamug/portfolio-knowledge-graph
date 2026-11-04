"""``kg_store.universe`` incremental asset-catalog deltas (Work item 28).

The store is an in-memory :class:`rdflib.Dataset` loaded with the full catalog the loader would
write for an initial ``universe.db``; the delta queries run against it exactly as they run against
GraphDB (the GraphDB-only explicit-statements ``FROM`` is dropped by the adapter and the dataset
unions its named graphs, as the explicit graph does). Every write goes through the real gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import rdflib
from fixtures.universe_rows import ROWS, Row, universe_db
from rdflib.namespace import RDF, XSD
from rdflib.query import ResultRow
from rdflib.term import Node, URIRef

from kg_store import gate, universe
from kg_store.graphdb import EXPLICIT_GRAPH, GraphDB

SCHEMA = Path(__file__).resolve().parent.parent / "schema"
KG = universe.KG
AS_OF = "2026-11-03"
REFERENCE = "urn:graph:reference"


class DatasetStore:
    """A read/write fake GraphDB backed by an in-memory dataset, for the delta tests."""

    def __init__(self, dataset: rdflib.Dataset) -> None:
        self.dataset = dataset
        self.repository = "test"
        self.host = "http://store.invalid"
        self.queries: list[str] = []
        self.added: list[tuple[bytes, str, str | None]] = []

    def _rows(self, sparql: str, *, lexical: bool) -> list[dict[str, Any]]:
        self.queries.append(sparql)
        query = sparql.replace(f"FROM <{EXPLICIT_GRAPH}> ", "")
        result = self.dataset.query(query)
        rows: list[dict[str, Any]] = []
        for row in result:
            assert isinstance(row, ResultRow)
            item: dict[str, Any] = {}
            for name in result.vars or ():
                term = row[name]
                if term is not None:
                    item[str(name)] = str(term) if lexical else term
            rows.append(item)
        return rows

    def select(self, sparql: str) -> list[dict[str, Any]]:
        return self._rows(sparql, lexical=True)

    def select_terms(self, sparql: str) -> list[dict[str, Node]]:
        return self._rows(sparql, lexical=False)

    def add(self, data: bytes, content_type: str, graph: str | None = None) -> None:
        assert graph is not None
        self.added.append((data, content_type, graph))
        self.dataset.graph(URIRef(graph)).parse(data=data, format="nt")

    @property
    def db(self) -> GraphDB:
        return cast(GraphDB, self)


def _store(
    tmp_path: Path, rows: list[Row] | None = None, *, universe_graph: bool = True
) -> DatasetStore:
    """A dataset holding ``reference.ttl`` and the full catalog of ``rows`` (or ``ROWS``)."""
    dataset = rdflib.Dataset(default_union=True)
    reference = rdflib.Graph().parse(SCHEMA / "reference.ttl", format="turtle")
    target = dataset.graph(URIRef(REFERENCE))
    for triple in reference:
        target.add(triple)
    if universe_graph:
        db = universe_db(tmp_path / "loaded.db", rows)
        batch = universe.plan(db, as_of=AS_OF)
        graph = dataset.graph(URIRef(batch.graph))
        for triple in gate.parse_batch(batch.data):
            graph.add(triple)
    return DatasetStore(dataset)


def _iri(local: str) -> str:
    return f"{KG}{local.lstrip(':')}"


def _batch(
    tmp_path: Path, initial: list[Row], now: list[Row]
) -> tuple[universe.DeltaBatch, DatasetStore]:
    store = _store(tmp_path, initial)
    return universe.plan_delta(universe_db(tmp_path / "now.db", now), store.db, as_of=AS_OF), store


# --- the four categories ----------------------------------------------------------------------
def test_a_store_loaded_from_the_same_source_has_an_empty_delta(tmp_path: Path) -> None:
    batch, store = _batch(tmp_path, ROWS, ROWS)
    assert not batch.actionable
    assert batch.new_assets == ()
    assert batch.new_memberships == ()
    assert batch.closures == ()
    assert batch.drift == ()
    assert batch.data == b""
    assert batch.triples == 0
    assert batch.graph == "urn:graph:universe:2026-Q4:delta:1"
    assert gate.check_target(batch.graph) is True
    universe.check_delta(batch, store.db)
    assert universe.write_delta(batch, store.db) == 0
    assert store.added == []


def test_a_new_ticker_is_a_new_asset_with_its_membership(tmp_path: Path) -> None:
    rows: list[Row] = [
        *ROWS,
        (
            "NEWCO",
            "New Company",
            "Information Technology",
            "Systems Software",
            "0002000001",
            "2024-01-02",
            None,
        ),
    ]
    batch, store = _batch(tmp_path, ROWS, rows)
    assert batch.new_assets == ("NEWCO",)
    assert batch.new_memberships == (_iri("UM_NEWCO_2024-01-02"),)
    assert batch.closures == ()
    assert batch.drift == ()
    parsed = gate.parse_batch(batch.data)
    assert (KG.NEWCO, RDF.type, KG.Asset) in parsed
    assert (KG.NEWCO, KG.tickerSymbol, rdflib.Literal("NEWCO")) in parsed
    assert (KG.NEWCO, KG.cikNumber, rdflib.Literal("0002000001")) in parsed
    assert (KG.NEWCO, KG.classifiedAs, KG.Ind_SoftwareServices) in parsed
    assert (KG["UM_NEWCO_2024-01-02"], KG.membershipAsset, KG.NEWCO) in parsed
    assert (KG.NEWCO, KG.hasUniverseMembership, KG["UM_NEWCO_2024-01-02"]) in parsed
    # The catalog's own universe and the stored assets are never re-declared.
    assert (KG.SP500Index, RDF.type, KG.Universe) not in parsed
    assert (KG.CEG, RDF.type, KG.Asset) not in parsed
    universe.check_delta(batch, store.db)
    assert universe.write_delta(batch, store.db) == batch.triples
    [(data, content_type, graph)] = store.added
    assert content_type == "application/n-triples"
    assert graph == batch.graph
    assert len(rdflib.Graph().parse(data=data, format="nt")) == batch.triples

    second = universe.plan_delta(tmp_path / "now.db", store.db, as_of=AS_OF)
    assert not second.actionable
    assert second.drift == ()
    assert universe.write_delta(second, store.db) == 0
    assert len(store.added) == 1

    third = universe.plan_delta(
        universe_db(
            tmp_path / "later.db",
            [*rows, ("LATER", "Later Co", None, None, None, "2024-02-02", None)],
        ),
        store.db,
        as_of=AS_OF,
    )
    assert third.new_assets == ("LATER",)
    assert third.graph == "urn:graph:universe:2026-Q4:delta:2"


def test_a_reference_asset_gets_a_new_membership_but_no_declaration(tmp_path: Path) -> None:
    now: list[Row] = [
        (
            "AAPL",
            "Apple Inc.",
            "Information Technology",
            "Technology Hardware, Storage & Peripherals",
            "0000320193",
            "2018-06-01",
            "2019-01-02",
        ),
        *ROWS,
    ]
    batch, store = _batch(tmp_path, ROWS, now)
    assert batch.new_assets == ()
    assert batch.new_memberships == (_iri("UM_AAPL_2018-06-01"),)
    assert batch.drift == ()
    parsed = gate.parse_batch(batch.data)
    assert (KG.AAPL, RDF.type, KG.Asset) not in parsed
    assert (KG["UM_AAPL_2018-06-01"], KG.membershipAsset, KG.AAPL) in parsed
    assert (KG.AAPL, KG.hasUniverseMembership, KG["UM_AAPL_2018-06-01"]) in parsed
    universe.check_delta(batch, store.db)
    assert universe.write_delta(batch, store.db) == batch.triples


def test_a_rename_joining_a_stored_asset_is_a_new_membership(tmp_path: Path) -> None:
    initial: list[Row] = [
        (
            "FB",
            "Facebook",
            "Communication Services",
            "Interactive Media & Services",
            "0001326801",
            "2019-07-01",
            "2022-06-08",
        ),
        (
            "META",
            "Meta Platforms",
            "Communication Services",
            "Interactive Media & Services",
            "0001326801",
            "2022-06-09",
            None,
        ),
    ]
    now: list[Row] = [
        (
            "FB",
            "Facebook",
            "Communication Services",
            "Interactive Media & Services",
            "0001326801",
            "2019-01-02",
            "2019-06-30",
        ),
        *initial,
    ]
    batch, store = _batch(tmp_path, initial, now)
    assert batch.new_assets == ()
    assert batch.new_memberships == (_iri("UM_FB_2019-01-02"),)
    assert batch.closures == ()
    assert batch.drift == ()
    parsed = gate.parse_batch(batch.data)
    assert (KG.META, RDF.type, KG.Asset) not in parsed
    assert (KG["UM_FB_2019-01-02"], KG.membershipAsset, KG.META) in parsed
    assert (KG.META, KG.hasUniverseMembership, KG["UM_FB_2019-01-02"]) in parsed
    universe.check_delta(batch, store.db)
    assert universe.write_delta(batch, store.db) == batch.triples
    assert not universe.plan_delta(tmp_path / "now.db", store.db, as_of=AS_OF).actionable


def test_a_closure_is_only_the_validto_triple(tmp_path: Path) -> None:
    now = [(*row[:6], "2026-01-15") if row[0] == "CEG" and row[6] is None else row for row in ROWS]
    batch, store = _batch(tmp_path, ROWS, now)
    membership = _iri("UM_CEG_2022-02-02")
    assert batch.new_assets == ()
    assert batch.new_memberships == ()
    assert batch.closures == ((membership, "2026-01-15"),)
    assert batch.drift == ()
    parsed = gate.parse_batch(batch.data)
    assert len(parsed) == 1
    assert set(parsed) == {
        (URIRef(membership), KG.validTo, rdflib.Literal("2026-01-15", datatype=XSD.date))
    }
    assert (URIRef(membership), RDF.type, None) not in parsed
    universe.check_delta(batch, store.db)
    assert universe.write_delta(batch, store.db) == 1
    assert not universe.plan_delta(tmp_path / "now.db", store.db, as_of=AS_OF).actionable


def test_a_reentry_is_a_new_membership_and_closes_the_old_one(tmp_path: Path) -> None:
    initial: list[Row] = [
        (
            "AAA",
            "Alpha Corp",
            "Utilities",
            "Electric Utilities",
            "0000000010",
            "2019-01-02",
            None,
        )
    ]
    now: list[Row] = [
        (
            "AAA",
            "Alpha Corp",
            "Utilities",
            "Electric Utilities",
            "0000000010",
            "2019-01-02",
            "2020-12-31",
        ),
        (
            "AAA",
            "Alpha Corp",
            "Utilities",
            "Electric Utilities",
            "0000000010",
            "2022-01-03",
            None,
        ),
    ]
    batch, store = _batch(tmp_path, initial, now)
    assert batch.new_assets == ()
    assert batch.new_memberships == (_iri("UM_AAA_2022-01-03"),)
    assert batch.closures == ((_iri("UM_AAA_2019-01-02"), "2020-12-31"),)
    assert batch.drift == ()
    parsed = gate.parse_batch(batch.data)
    assert (KG.AAA, RDF.type, KG.Asset) not in parsed
    assert (KG["UM_AAA_2022-01-03"], RDF.type, KG.UniverseMembership) in parsed
    assert (KG.AAA, KG.hasUniverseMembership, KG["UM_AAA_2022-01-03"]) in parsed
    universe.check_delta(batch, store.db)
    universe.write_delta(batch, store.db)
    assert not universe.plan_delta(tmp_path / "now.db", store.db, as_of=AS_OF).actionable


# --- drift is reported and never written ------------------------------------------------------
def test_a_changed_sector_name_and_cik_are_drift_and_are_not_written(tmp_path: Path) -> None:
    now = [
        (
            "CEG",
            "Constellation Energy Corp",
            "Energy",
            "Oil & Gas Exploration & Production",
            "0001868276",
            "2022-02-02",
            None,
        )
        if row[0] == "CEG" and row[6] is None
        else row
        for row in ROWS
    ]
    batch, store = _batch(tmp_path, ROWS, now)
    assert not batch.actionable
    assert batch.new_assets == ()
    assert batch.new_memberships == ()
    assert batch.closures == ()
    assert any("companyName differs" in line for line in batch.drift)
    assert any("cikNumber differs" in line for line in batch.drift)
    assert any("classifiedAs differs" in line for line in batch.drift)
    assert batch.data == b""
    assert universe.write_delta(batch, store.db) == 0
    assert store.added == []


def test_a_stored_membership_absent_from_the_source_is_drift(tmp_path: Path) -> None:
    initial: list[Row] = [
        *ROWS,
        (
            "EXTRA",
            "Extra Corp",
            "Industrials",
            "Aerospace & Defense",
            "0000000011",
            "2021-01-04",
            None,
        ),
    ]
    batch, store = _batch(tmp_path, initial, ROWS)
    assert not batch.actionable
    assert any(":EXTRA: stored but absent from the source" in line for line in batch.drift)
    assert any(
        ":UM_EXTRA_2021-01-04: stored but absent from the source" in line for line in batch.drift
    )
    assert universe.write_delta(batch, store.db) == 0
    assert store.added == []


# --- refusals ---------------------------------------------------------------------------------
def test_a_store_without_the_full_catalog_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path, universe_graph=False)
    with pytest.raises(universe.UniverseDeltaError, match="full catalog"):
        universe.plan_delta(universe_db(tmp_path / "now.db"), store.db, as_of=AS_OF)


def test_a_store_without_reference_assets_is_refused(tmp_path: Path) -> None:
    store = DatasetStore(rdflib.Dataset(default_union=True))
    with pytest.raises(universe.UniverseDeltaError, match=r"reference\.ttl"):
        universe.plan_delta(universe_db(tmp_path / "now.db"), store.db, as_of=AS_OF)


def test_the_gate_refuses_an_existing_delta_graph(tmp_path: Path) -> None:
    rows: list[Row] = [
        *ROWS,
        ("NEWCO", "New Company", "Information Technology", "Systems Software", "0002000001",
         "2024-01-02", None),
    ]  # fmt: skip
    batch, store = _batch(tmp_path, ROWS, rows)
    universe.write_delta(batch, store.db)
    with pytest.raises(gate.IngestRejected, match="already exists"):
        gate.ingest(store.db, batch.data, batch.graph)


def test_the_gate_refuses_a_redeclared_stored_asset(tmp_path: Path) -> None:
    store = _store(tmp_path)
    full = universe.plan(universe_db(tmp_path / "now.db"), as_of=AS_OF)
    with pytest.raises(gate.IngestRejected, match="already exist in the store"):
        gate.ingest(store.db, full.data, "urn:graph:universe:2027-Q1")


def test_the_gate_refuses_a_closure_before_the_opening_date(tmp_path: Path) -> None:
    store = _store(tmp_path)
    batch = (
        b"@prefix : <https://thesis.local/kg/portfolio#> .\n"
        b"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        b':UM_CEG_2022-02-02 :validTo "2021-01-01"^^xsd:date .\n'
    )
    with pytest.raises(gate.IngestRejected, match="not after the date it opened"):
        gate.ingest(store.db, batch, "urn:graph:universe:2026-Q4:delta:9")


# --- the CLI contract -------------------------------------------------------------------------
def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    store: DatasetStore,
    db: Path,
    *args: str,
) -> tuple[int, str, str]:
    monkeypatch.setenv("SQL_UNIVERSE_DB", str(db))
    monkeypatch.setattr(universe.GraphDB, "from_env", classmethod(lambda cls: store.db))
    code = universe.main(["--delta", "--as-of", AS_OF, *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_delta_cli_dry_run_reports_the_categories_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store(tmp_path, ROWS)
    now = [(*row[:6], "2026-01-15") if row[0] == "CEG" and row[6] is None else row for row in ROWS]
    db = universe_db(tmp_path / "now.db", now)
    code, out, _ = _run_main(monkeypatch, capsys, store, db)
    assert code == 0
    assert "delta: 0 new asset(s), 0 new membership(s), 1 closure(s), 0 drift item(s)" in out
    assert "target graph: urn:graph:universe:2026-Q4:delta:1" in out
    assert "closures: :UM_CEG_2022-02-02 validTo 2026-01-15" in out
    assert "pre-flight: would-be-written" in out
    assert "dry run, nothing written" in out
    assert store.added == []


def test_the_delta_cli_write_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store(tmp_path, ROWS)
    rows: list[Row] = [
        *ROWS,
        (
            "NEWCO",
            "New Company",
            "Information Technology",
            "Systems Software",
            "0002000001",
            "2024-01-02",
            None,
        ),
    ]
    db = universe_db(tmp_path / "now.db", rows)
    code, out, _ = _run_main(monkeypatch, capsys, store, db, "--write")
    assert code == 0
    assert "written: 10 triples to urn:graph:universe:2026-Q4:delta:1" in out
    assert len(store.added) == 1

    code, out, _ = _run_main(monkeypatch, capsys, store, db, "--write")
    assert code == 0
    assert "delta: 0 new asset(s), 0 new membership(s), 0 closure(s), 0 drift item(s)" in out
    assert "empty delta: nothing to write" in out
    assert len(store.added) == 1


def test_the_delta_cli_refuses_a_production_write_without_the_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store(tmp_path, ROWS)
    store.repository = "portfolio"
    db = universe_db(tmp_path / "now.db", ROWS)
    with pytest.raises(SystemExit) as info:
        _run_main(monkeypatch, capsys, store, db, "--write")
    assert info.value.code == 2
    assert "needs --to-production" in capsys.readouterr().err
