"""``cli/ingest.py --check``: it reports a batch's undeclared references, not a bare class error (T-146).

The script runs as a subprocess (constitution #10), so these tests write their own small Turtle
batches and share nothing with ``test_kg_gate.py``, whose helpers read the worked example in process.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from conftest import FakeGraphDB

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "cli" / "ingest.py"
PREFIXES = "@prefix : <https://thesis.local/kg/portfolio#> .\n"
GRAPH = "urn:graph:derived:entity-resolution:2026-08-05"
COOCCURRENCE = (
    ':c a :AssetCoOccurrence ; :coOccurrenceAsset :A, :B ; :coOccurrenceKind "SHARED_EXECUTIVE_CANDIDATE" ;'
    ' :coOccurrenceMethod "m" ; :coOccurrenceWeight 1.0 .\n'
)


def _check(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    batch = tmp_path / "batch.ttl"
    batch.write_text(PREFIXES + body)
    return subprocess.run(  # noqa: S603 - fixed interpreter and our own script
        [sys.executable, str(CLI), str(batch), "--graph", GRAPH, "--check"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_says_why_a_batch_with_undeclared_references_is_rejected(tmp_path: Path) -> None:
    result = _check(tmp_path, COOCCURRENCE)
    assert result.returncode == 2
    assert "does not declare" in result.stderr
    assert "--check cannot read them from the store" in result.stderr


def test_check_accepts_a_batch_that_declares_what_it_points_at(tmp_path: Path) -> None:
    declared = (
        COOCCURRENCE
        + ':A a :Asset ; :tickerSymbol "A" ; :cikNumber "1" .\n'
        + ':B a :Asset ; :tickerSymbol "B" ; :cikNumber "2" .\n'
    )
    result = _check(tmp_path, declared)
    assert result.returncode == 0, result.stderr


def test_check_does_not_blame_references_for_an_unrelated_rejection(tmp_path: Path) -> None:
    result = _check(tmp_path, ":a a :ScoreSnapshott .\n")
    assert result.returncode == 2
    assert "does not declare" not in result.stderr


def test_check_says_it_cannot_verify_what_a_closing_triple_closes(tmp_path: Path) -> None:
    closing = ':m :validTo "2026-03-31"^^<http://www.w3.org/2001/XMLSchema#date> .\n'
    result = _check(tmp_path, closing)
    assert result.returncode == 0, result.stderr
    assert "closes stored records" in result.stderr
    assert "closes stored records" not in _check(tmp_path, ":x a :Asset .\n").stderr


def _ingest_main(fake: FakeGraphDB, monkeypatch: pytest.MonkeyPatch) -> Callable[[list[str]], int]:
    """``cli/ingest.py``'s ``main``, loaded in process with ``GraphDB.from_env`` returning ``fake``
    (a refusal by the store-reading checks needs a store, and the subprocess tests have none)."""
    spec = importlib.util.spec_from_file_location("cli_ingest_in_process", CLI)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "GraphDB", types.SimpleNamespace(from_env=lambda: fake.db))
    return cast("Callable[[list[str]], int]", module.main)


@pytest.mark.parametrize(
    ("holds", "code"),
    [(True, 0), (False, 2)],  # a stored open membership is closed; an unknown subject is refused
)
def test_a_refused_closure_exits_2_and_writes_nothing(
    holds: bool,
    code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_db: Callable[..., FakeGraphDB],
) -> None:
    kg = "https://thesis.local/kg/portfolio#"
    rows = (
        [
            {
                "s": kg + "m",
                "p": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                "o": kg + "UniverseMembership",
            }
        ]
        if holds
        else []
    )
    fake = make_db()

    def select(sparql: str) -> list[dict[str, str]]:  # only the closing query finds anything
        return rows if "VALUES ?s {" in sparql and "VALUES ?p {" in sparql else []

    fake.select = select  # type: ignore[method-assign]
    batch = tmp_path / "batch.ttl"
    batch.write_text(
        PREFIXES + ':m :validTo "2026-03-31"^^<http://www.w3.org/2001/XMLSchema#date> .\n'
    )
    main = _ingest_main(fake, monkeypatch)
    assert main([str(batch), "--graph", "urn:graph:universe:2026-Q1"]) == code
    assert len(fake.added) == (1 if holds else 0)
