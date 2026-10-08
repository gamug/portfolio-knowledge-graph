"""Exit codes of ``cli/verify_store.py``, ``cli/load_schema.py`` and ``cli/ingest.py`` against a real
GraphDB (T-175; constitution Code & Git #9).

Opt in with ``uv run pytest -m integration tests/test_store_cli_exit_codes.py``; skipped when the
store in ``.env`` is unreachable. ``verify_store`` writes nothing, so one test runs it on the
configured repository (only when that is ``portfolio``, the store that must match ``schema/``).
Where a CLI writes, the test runs it on a scratch repository created from
``schema/graphdb-repo-config.ttl`` under a name of its own and deleted afterwards: never
``portfolio`` (the guard is checked before anything is created or deleted). The two tests that
point a CLI at a repository that does not exist need none. The application user cannot create a
repository (HTTP 403), so the scratch tests use the account in ``KG_ADMIN_USER``/
``KG_ADMIN_PASSWORD`` (``.env.example``) and skip only when ``KG_ADMIN_USER`` is not set: with it
set, an account that cannot create a repository (a wrong password, say) fails the test.

A run killed in the middle leaves its ``kgtest-...`` repository behind: delete it in the Workbench
(Setup -> Repositories) or with ``DELETE {KG_HOST}/rest/repositories/<id>``.
"""

from __future__ import annotations

import importlib.util
import os
import re
import secrets
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import cast
from urllib.parse import quote

import pytest

from kg_store import load_schema
from kg_store.graphdb import PRODUCTION_REPOSITORY, GraphDB, GraphDBError, schema_dir

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
BATCH = (
    b"@prefix : <https://thesis.local/kg/portfolio#> .\n"
    b':a a :Asset ; :tickerSymbol "AAA" ; :cikNumber "0000000001" .\n'
)
GRAPH = "urn:graph:ingest:ORCHESTRATOR:2026-10-08"


def _cli(name: str) -> Callable[..., int]:
    spec = importlib.util.spec_from_file_location(f"cli_{name}", ROOT / "cli" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("Callable[..., int]", module.main)


@pytest.fixture(scope="module")
def configured() -> GraphDB:
    """The store in ``.env``, or a skip when it cannot be reached."""
    try:
        db = GraphDB.from_env()
        db.size()
    except GraphDBError as exc:
        pytest.skip(f"no reachable GraphDB: {exc}")
    return db


def _create(db: GraphDB, name: str) -> None:
    if name == PRODUCTION_REPOSITORY:
        raise AssertionError("the scratch repository must not be the production one")
    config = (schema_dir() / "graphdb-repo-config.ttl").read_text()
    config, n = re.subn(r'rep:repositoryID\s+"[^"]*"', f'rep:repositoryID "{name}"', config)
    assert n == 1, "graphdb-repo-config.ttl no longer has one rep:repositoryID"
    boundary = secrets.token_hex(8)
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="config"; filename="config.ttl"\r\n'
        "Content-Type: text/turtle\r\n\r\n"
        f"{config}\r\n--{boundary}--\r\n"
    ).encode()
    db._request(
        "POST", f"{db.host}/rest/repositories", body, f"multipart/form-data; boundary={boundary}"
    )


def _delete(db: GraphDB, name: str) -> None:
    if name == PRODUCTION_REPOSITORY or not name.startswith("kgtest-"):
        raise AssertionError(f"refusing to delete {name!r}")
    db._request("DELETE", f"{db.host}/rest/repositories/{quote(name)}")


@pytest.fixture
def scratch(configured: GraphDB, monkeypatch: pytest.MonkeyPatch) -> Iterator[GraphDB]:
    """An empty repository of its own, which ``KG_REPOSITORY`` names for the test."""
    user = os.environ.get("KG_ADMIN_USER", "")
    if not user:
        pytest.skip(
            "set KG_ADMIN_USER and KG_ADMIN_PASSWORD: the application user cannot create a repository"
        )
    password = os.environ.get("KG_ADMIN_PASSWORD", "")
    name = f"kgtest-{uuid.uuid4().hex[:12]}"
    admin = GraphDB(configured.host, name, user, password)
    _create(admin, name)
    monkeypatch.setenv("KG_REPOSITORY", name)
    monkeypatch.setenv("KG_USER", user)
    monkeypatch.setenv("KG_PASSWORD", password)
    try:
        yield admin
    finally:
        _delete(admin, name)


def test_verify_store_passes_on_the_configured_store(configured: GraphDB) -> None:
    if configured.repository != PRODUCTION_REPOSITORY:
        pytest.skip(f"KG_REPOSITORY is {configured.repository}, not {PRODUCTION_REPOSITORY}")
    assert _cli("verify_store")() == 0


def test_verify_store_fails_on_an_empty_store_and_passes_after_the_schema_is_loaded(
    scratch: GraphDB,
) -> None:
    verify = _cli("verify_store")
    assert verify() == 1
    assert load_schema.main([]) == 0
    assert verify() == 0


def test_load_schema_exits_0_twice_and_1_on_an_unreadable_directory(
    scratch: GraphDB, tmp_path: Path
) -> None:
    assert load_schema.main([]) == 0
    assert load_schema.main([]) == 0, "loading again replaces the graphs, so it still matches"
    assert load_schema.main(["--dir", str(tmp_path / "absent")]) == 1


def test_load_schema_exits_1_when_the_repository_does_not_exist(
    configured: GraphDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KG_REPOSITORY", f"kgtest-absent-{uuid.uuid4().hex[:8]}")
    assert load_schema.main([]) == 1


def test_ingest_exits_0_then_2_for_a_graph_that_exists_and_for_a_batch_that_fails_the_shapes(
    scratch: GraphDB, tmp_path: Path
) -> None:
    ingest = _cli("ingest")
    good = tmp_path / "good.ttl"
    good.write_bytes(BATCH)
    bad = tmp_path / "bad.ttl"
    bad.write_bytes(BATCH.replace(b"AAA", b"BBB").replace(b"0000000001", b"1"))
    other = tmp_path / "other.ttl"
    other.write_bytes(BATCH.replace(b":a a", b":b a").replace(b"AAA", b"CCC"))
    assert ingest([str(good), "--graph", GRAPH]) == 0
    assert scratch.explicit_graph_sizes()[GRAPH] == 3
    # a new individual, so only the "graph already exists" rule can refuse this one
    assert ingest([str(other), "--graph", GRAPH]) == 2
    assert scratch.explicit_graph_sizes()[GRAPH] == 3
    assert ingest([str(bad), "--graph", "urn:graph:ingest:ORCHESTRATOR:2026-10-09"]) == 2
    assert "urn:graph:ingest:ORCHESTRATOR:2026-10-09" not in scratch.explicit_graph_sizes()


def test_ingest_exits_1_for_a_missing_file_and_for_a_repository_that_does_not_exist(
    configured: GraphDB, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingest = _cli("ingest")
    good = tmp_path / "good.ttl"
    good.write_bytes(BATCH)
    assert ingest([str(tmp_path / "absent.ttl"), "--graph", GRAPH]) == 1
    monkeypatch.setenv("KG_REPOSITORY", f"kgtest-absent-{uuid.uuid4().hex[:8]}")
    assert ingest([str(good), "--graph", GRAPH]) == 1
