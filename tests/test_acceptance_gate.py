"""``acceptance.check_gate`` reads pyshacl's results graph, not its text report (T-142)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
import rdflib
from rdflib.namespace import SH

from kg_store import acceptance
from kg_store.gate import IngestRejected, ShaclRejected, parse_batch, validate
from kg_store.graphdb import GraphDB


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
    results = rejection.results
    found = [
        (results.value(r, SH.resultPath), results.value(r, SH.sourceConstraintComponent))
        for r in results.subjects(rdflib.RDF.type, SH.ValidationResult)
    ]
    assert found == [acceptance.EXPECTED_VIOLATION]


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
    assert len(list(rejection.results.subjects(rdflib.RDF.type, SH.ValidationResult))) == 1
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
