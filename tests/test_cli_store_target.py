"""Target banner and production guards of the store CLIs (Work item 39).

Hermetic: every command points at ``http://host.invalid``; the guard tests stop before any
request, and the "past the guard" tests fail at the unreachable host, which proves the flag
reached the connection path without a real GraphDB.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOAD_SCHEMA = ROOT / "cli" / "load_schema.py"
VERIFY_STORE = ROOT / "cli" / "verify_store.py"
TARGET = "target: GraphDB http://host.invalid repository portfolio [PRODUCTION]"


def _run(
    script: Path, *args: str, repository: str = "portfolio"
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KG_HOST": "http://host.invalid",
        "KG_REPOSITORY": repository,
        "KG_USER": "banner-user-secret",
        "KG_PASSWORD": "banner-password-secret",
    }
    return subprocess.run(  # noqa: S603 -- fixed interpreter and script, no local store
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_help_does_not_announce_a_target() -> None:
    result = _run(LOAD_SCHEMA, "--help")
    assert result.returncode == 0
    assert "--to-production" in result.stdout
    assert "target:" not in result.stdout
    result = _run(VERIFY_STORE, "--help")
    assert result.returncode == 0
    assert "--to-production" in result.stdout
    assert "target:" not in result.stdout


def test_load_schema_exits_2_on_production_without_the_flag() -> None:
    result = _run(LOAD_SCHEMA)
    assert result.returncode == 2
    assert result.stdout.splitlines()[0] == TARGET
    assert "--to-production is required" in result.stderr
    assert "banner-user-secret" not in result.stdout + result.stderr
    assert "banner-password-secret" not in result.stdout + result.stderr


def test_load_schema_proceeds_past_the_guard_with_the_flag() -> None:
    result = _run(LOAD_SCHEMA, "--to-production")
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == TARGET
    assert "--to-production is required" not in result.stderr
    assert "cannot reach GraphDB" in result.stderr


def test_verify_store_exits_2_on_production_without_the_flag() -> None:
    result = _run(VERIFY_STORE)
    assert result.returncode == 2
    assert result.stdout.splitlines()[0] == TARGET
    assert "--to-production is required" in result.stderr
    assert "PASS" not in result.stdout and "FAIL" not in result.stdout


def test_verify_store_proceeds_past_the_guard_with_the_flag() -> None:
    result = _run(VERIFY_STORE, "--to-production")
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == TARGET
    assert "--to-production is required" not in result.stderr
    assert "FAIL" in result.stdout
