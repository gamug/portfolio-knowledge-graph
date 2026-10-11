"""``kg_store.acceptance``: ``check_gate`` reads pyshacl's results graph, not its text report (T-142); ``check_string_terms`` (T-181)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
import rdflib
from conftest import FakeGraphDB

from kg_store import acceptance
from kg_store.gate import (
    IngestRejected,
    ShaclRejected,
    load_gate_schema,
    parse_batch,
    references,
    validate,
)
from kg_store.graphdb import GraphDB, schema_dir

KG = rdflib.Namespace("https://thesis.local/kg/portfolio#")


def _db() -> GraphDB:
    return cast(GraphDB, FakeDB())


class FakeDB:
    """Just what ``check_gate`` touches: a constant size and an empty probe graph."""

    def size(self) -> int:
        return 7

    def select(self, query: str) -> list[dict[str, str]]:
        return []


def test_probe_is_rejected_with_one_min_count_result() -> None:
    rejection = _rejection(acceptance.MALFORMED)
    assert isinstance(rejection, IngestRejected)
    assert acceptance.violations(rejection.results) == [acceptance.EXPECTED_VIOLATION]


def test_check_gate_passes_on_the_probe() -> None:
    assert "store size unchanged at 7" in acceptance.check_gate(_db())


def test_check_gate_ignores_report_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    real = ShaclRejected("a different wording entirely", _rejection(acceptance.MALFORMED).results)
    monkeypatch.setattr(acceptance, "ingest", _raiser(real))
    assert "unchanged" in acceptance.check_gate(_db())


def test_check_gate_fails_on_a_second_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    batch = acceptance.MALFORMED.replace(b':agentOrigin "SEMANTIC" ;', b"")
    monkeypatch.setattr(acceptance, "ingest", _raiser(_rejection(batch)))
    with pytest.raises(AssertionError, match="only violation"):
        acceptance.check_gate(_db())


def test_check_gate_fails_on_one_violation_of_another_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly one result is not enough: it must be the :timestamp minCount one."""
    batch = acceptance.MALFORMED.replace(
        b':rawValue "-0.5"^^xsd:decimal ;', b':timestamp "2099-01-01T00:00:00"^^xsd:dateTime ;'
    )
    rejection = _rejection(batch)
    assert len(acceptance.violations(rejection.results)) == 1
    monkeypatch.setattr(acceptance, "ingest", _raiser(rejection))
    with pytest.raises(AssertionError, match="only violation"):
        acceptance.check_gate(_db())


def test_check_gate_fails_when_rejected_but_not_by_shacl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceptance, "ingest", _raiser(IngestRejected("bad graph name")))
    with pytest.raises(AssertionError, match="not by SHACL"):
        acceptance.check_gate(_db())


def test_check_gate_fails_when_the_batch_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceptance, "ingest", lambda *a, **k: 1)
    with pytest.raises(AssertionError, match="accepted"):
        acceptance.check_gate(_db())


def _rejection(batch: bytes) -> ShaclRejected:
    with pytest.raises(ShaclRejected) as info:
        validate(parse_batch(batch))
    return info.value


def _raiser(exc: Exception) -> Callable[..., int]:
    def raise_(*args: object, **kwargs: object) -> int:
        raise exc

    return raise_


def _stored_portfolios(kind: rdflib.term.Node | None = None) -> list[dict[str, rdflib.term.Node]]:
    """What the store holds about the Portfolios of the quant batch once ``instances.trig`` and ``reference.ttl`` are loaded."""
    schema = schema_dir()
    dataset = rdflib.Dataset(default_union=False)
    dataset.parse(schema / "instances.trig", format="trig")
    batch = dataset.graph(rdflib.URIRef(acceptance.QUANT_GRAPH))
    refs = references(batch, load_gate_schema(schema))
    rows = []
    others = [*dataset.graphs(), rdflib.Graph().parse(schema / "reference.ttl", format="turtle")]
    for graph in others:  # the Assets are typed in reference.ttl
        for ref in refs:
            for p, o in graph.predicate_objects(ref):
                stored = kind if kind is not None and p == KG.portfolioKind else o
                rows.append({"s": ref, "p": p, "o": stored})
    return rows


def test_check_string_terms_passes_beside_the_stored_portfolios() -> None:
    fake = FakeGraphDB(terms=_stored_portfolios())
    assert "passes beside" in acceptance.check_string_terms(fake.db)


def test_check_string_terms_fails_for_a_kind_stored_in_another_form() -> None:
    """A kind read back typed ``xsd:string`` no longer satisfies the shape's ``sh:in``."""
    typed = rdflib.Literal("LIVE", datatype=rdflib.XSD.string)
    with pytest.raises(AssertionError, match="fails beside the store"):
        acceptance.check_string_terms(FakeGraphDB(terms=_stored_portfolios(typed)).db)


def test_check_string_terms_fails_when_the_store_holds_no_portfolio() -> None:
    with pytest.raises(AssertionError, match="fails beside the store"):
        acceptance.check_string_terms(FakeGraphDB().db)
