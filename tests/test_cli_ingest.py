"""``cli/ingest.py --check``: it reports a batch's undeclared references, not a bare class error (T-146)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
