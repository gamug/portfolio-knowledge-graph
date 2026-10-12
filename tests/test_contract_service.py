"""``projection.contract_check`` against a service's contract endpoints (T-173).

Hermetic: a fake ``fetch`` for the functions, and a throwaway HTTP server on localhost for the
CLI, which runs as a subprocess (constitution #10). Nothing here needs upstream or its network.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import urllib.error
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from support import load_cli

from projection import contract_check
from projection.contract_check import ContractFetchError, DatabaseState, DeclaredContract
from projection.expectations import ExpectationError, SourceExpectation
from projection.view_contract import VIEW_COLUMNS

CLI = Path(__file__).resolve().parent.parent / "cli" / "check_view_contract.py"
BASE = "http://service.test/api/v1"


def _contract(version: int = 10) -> dict[str, Any]:
    """What ``/contract`` answers when upstream matches the pin exactly."""
    return {
        "contract_version": version,
        "code_version": "abc1234",
        "views": [
            {"name": view, "frozen": False, "columns": [{"name": c} for c in columns]}
            for view, columns in VIEW_COLUMNS.items()
        ],
    }


def _database(schema_version: int = 10, missing: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "views_present": [v for v in VIEW_COLUMNS if v not in missing],
        "views_missing": list(missing),
    }


def _fetcher(routes: dict[str, Any]) -> Any:
    def fetch(url: str) -> Any:
        path = url.removeprefix(BASE)
        value = routes[path]
        if isinstance(value, Exception):
            raise value
        return value

    return fetch


def _declared(version: int = 10, schema_version: int | None = 10) -> DeclaredContract:
    routes: dict[str, Any] = {"/contract": _contract(version)}
    routes["/contract/database"] = (
        _database(schema_version)
        if schema_version is not None
        else urllib.error.HTTPError(BASE, 404, "not found", None, None)  # type: ignore[arg-type]
    )
    return contract_check.fetch_contract(BASE, _fetcher(routes))


def _pin(floor: int = 9, contract: int | None = 10) -> SourceExpectation:
    # A synthetic pin with its own numbers, not the shipped one (that is asserted in test_expectations).
    return SourceExpectation(floor, ("REPLAY",), contract)


# --- the version guard: the cases the task lists ---------------------------------------------


def test_equal_versions_pass() -> None:
    report = contract_check.check_service(_declared(10, 10), _pin(contract=10))
    assert report.drift == []
    assert not any("lags" in n for n in report.notes)


def test_a_different_contract_version_fails() -> None:
    report = contract_check.check_service(_declared(12, 12), _pin(contract=10))
    assert report.drift == [
        "contract_version: the service declares 12, the pin records 10 (re-pin, T-157)"
    ]


def test_a_database_below_the_floor_fails() -> None:
    report = contract_check.check_service(_declared(10, 8), _pin(floor=9, contract=10))
    assert any("schema_version 8 is below the floor 9" in d for d in report.drift)


def test_a_database_above_the_floor_passes_on_its_number() -> None:
    report = contract_check.check_service(_declared(12, 11), _pin(floor=9, contract=12))
    assert report.drift == []


def test_a_database_below_the_declared_contract_only_warns() -> None:
    report = contract_check.check_service(_declared(12, 10), _pin(floor=9, contract=12))
    assert report.drift == []
    assert any("lags its code: schema_version 10, contract_version 12" in n for n in report.notes)


def test_a_pin_without_the_key_skips_the_version_check_with_a_notice() -> None:
    report = contract_check.check_service(_declared(12, 12), _pin(contract=None))
    assert report.drift == []
    assert any("the pin records none" in n and "skipped" in n for n in report.notes)


def test_a_service_without_the_database_route_is_noted_not_failed() -> None:
    report = contract_check.check_service(_declared(10, None), _pin(contract=10))
    assert report.drift == []
    assert any("does not offer /contract/database" in n for n in report.notes)


def test_a_database_newer_than_its_code_is_a_note() -> None:
    report = contract_check.check_service(_declared(10, 11), _pin(contract=10))
    assert report.drift == []
    assert any(
        "newer than its code: schema_version 11, contract_version 10" in n for n in report.notes
    )


@pytest.mark.parametrize("break_it", ["drop_one", "add_one", "duplicate"])
def test_views_that_do_not_partition_the_contract_are_refused(break_it: str) -> None:
    database = _database(10)
    if break_it == "drop_one":
        database["views_present"].pop()
    elif break_it == "add_one":
        database["views_missing"].append("v_not_in_the_contract")
    else:
        database["views_missing"].append(database["views_present"][0])
    routes = {"/contract": _contract(10), "/contract/database": database}
    with pytest.raises(ContractFetchError, match="must together be exactly"):
        contract_check.fetch_contract(BASE, _fetcher(routes))


def test_a_pinned_view_the_database_lacks_is_drift() -> None:
    routes = {"/contract": _contract(10), "/contract/database": _database(10, ("v_veto",))}
    declared = contract_check.fetch_contract(BASE, _fetcher(routes))
    report = contract_check.check_service(declared, _pin(contract=10))
    assert report.drift == [
        "database lacks pinned views ['v_veto'] (a projector reading them would fail)"
    ]


def test_a_view_we_do_not_pin_that_the_database_lacks_is_a_note() -> None:
    body = _contract(10)
    body["views"].append(  # a view upstream has and we deliberately do not read (NOT_READ)
        {"name": "v_universe_membership", "frozen": True, "columns": [{"name": "id"}]}
    )
    database = _database(10)
    database["views_missing"] = ["v_universe_membership"]
    routes = {"/contract": body, "/contract/database": database}
    declared = contract_check.fetch_contract(BASE, _fetcher(routes))
    report = contract_check.check_service(declared, _pin(contract=10))
    assert report.drift == []
    assert any("lacks views we do not pin ['v_universe_membership']" in n for n in report.notes)


# --- the column comparison over the wire -----------------------------------------------------


def test_a_removed_pinned_column_is_drift_and_an_added_one_a_note() -> None:
    body = _contract()
    view = body["views"][0]
    removed = view["columns"].pop(0)["name"]
    body["views"][1]["columns"].append({"name": "added_later"})
    declared = contract_check.fetch_contract(
        BASE, _fetcher({"/contract": body, "/contract/database": _database()})
    )
    report = contract_check.check_service(declared, _pin(contract=10))
    assert f"{view['name']}: pinned columns removed ['{removed}']" in report.drift
    assert any("columns added upstream ['added_later']" in n for n in report.notes)


# --- fetch_contract refuses what is not the contract -----------------------------------------


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ([], "no integer 'contract_version'"),
        ({"contract_version": "10", "views": []}, "no integer 'contract_version'"),
        ({"contract_version": True, "views": []}, "no integer 'contract_version'"),
        ({"contract_version": 10}, "no 'views' list"),
        ({"contract_version": 10, "views": [{"name": "v"}]}, "malformed view entry"),
        ({"contract_version": 10, "views": [{"name": "v", "columns": ["x"]}]}, "columns must be"),
    ],
)
def test_a_body_that_is_not_the_contract_is_refused(body: Any, why: str) -> None:
    with pytest.raises(ContractFetchError, match=why):
        contract_check.fetch_contract(BASE, _fetcher({"/contract": body}))


def test_a_view_listed_twice_is_refused() -> None:
    body = _contract()
    body["views"].append(body["views"][0])
    with pytest.raises(ContractFetchError, match="appears twice"):
        contract_check.fetch_contract(BASE, _fetcher({"/contract": body}))


def test_a_database_body_without_a_version_is_refused() -> None:
    routes = {"/contract": _contract(), "/contract/database": {"views_present": []}}
    with pytest.raises(ContractFetchError, match="no integer 'schema_version'"):
        contract_check.fetch_contract(BASE, _fetcher(routes))


def test_an_unreachable_service_is_an_error_not_drift() -> None:
    routes = {"/contract": urllib.error.URLError("connection refused")}
    with pytest.raises(ContractFetchError, match="cannot read"):
        contract_check.fetch_contract(BASE, _fetcher(routes))


def test_a_server_error_on_the_database_route_is_an_error() -> None:
    boom = urllib.error.HTTPError(BASE, 500, "boom", None, None)  # type: ignore[arg-type]
    routes = {"/contract": _contract(), "/contract/database": boom}
    with pytest.raises(ContractFetchError, match="cannot read"):
        contract_check.fetch_contract(BASE, _fetcher(routes))


def test_a_404_on_the_contract_route_says_the_url_should_end_at_the_prefix() -> None:
    gone = urllib.error.HTTPError(BASE, 404, "not found", None, None)  # type: ignore[arg-type]
    with pytest.raises(ContractFetchError, match="should end at the API prefix"):
        contract_check.fetch_contract(BASE, _fetcher({"/contract": gone}))


def test_only_http_urls_are_read() -> None:
    with pytest.raises(ContractFetchError, match="not an http"):
        contract_check.fetch_contract("file:///etc/passwd", _fetcher({}))


def test_the_database_state_is_what_the_service_said() -> None:
    declared = _declared(10, 9)
    assert declared.database == DatabaseState(9, tuple(VIEW_COLUMNS), ())
    assert declared.code_version == "abc1234"


# --- the CLI, as a subprocess against a local server -----------------------------------------


@contextmanager
def _serve(routes: dict[str, tuple[int, Any]]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = routes.get(self.path, (404, {}))
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_: object) -> None:  # silence the test output
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _run(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and script, a localhost URL
        [sys.executable, str(CLI), url], capture_output=True, text=True, check=False, timeout=60
    )


def test_cli_exits_0_for_a_service_that_matches_the_pin_and_checks_its_contract_version() -> None:
    routes = {
        "/api/v1/contract": (200, _contract(12)),
        "/api/v1/contract/database": (200, _database(12)),
    }
    with _serve(routes) as url:
        result = _run(url)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "view contract: OK" in result.stdout
    # the shipped pin records contract_version 12 (T-157), so the check runs and nothing is skipped
    assert "the pin records none" not in result.stdout


def test_cli_exits_1_when_the_service_serves_another_contract_version() -> None:
    routes = {
        "/api/v1/contract": (200, _contract(13)),
        "/api/v1/contract/database": (200, _database(13)),
    }
    with _serve(routes) as url:
        result = _run(url)
    assert result.returncode == 1
    assert "DRIFT contract_version: the service declares 13, the pin records 12" in result.stdout


def test_cli_exits_1_when_the_database_is_below_the_floor() -> None:
    routes = {
        "/api/v1/contract": (200, _contract(12)),
        "/api/v1/contract/database": (200, _database(8)),
    }
    with _serve(routes) as url:
        result = _run(url)
    assert result.returncode == 1
    assert "DRIFT database: schema_version 8 is below the floor 12" in result.stdout


def test_cli_exits_2_when_the_service_answers_something_else() -> None:
    with _serve({"/api/v1/contract": (200, {"hello": "world"})}) as url:
        result = _run(url)
    assert result.returncode == 2
    assert "error:" in result.stderr


def test_cli_exits_2_when_nothing_listens() -> None:
    with socket.socket() as probe:  # a port that was free a moment ago, now closed
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = _run(f"http://127.0.0.1:{port}/api/v1")
    assert result.returncode == 2
    assert "cannot read" in result.stderr


def test_an_answer_longer_than_the_cap_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contract_check, "_MAX_BODY_BYTES", 100)
    with (
        _serve({"/api/v1/contract": (200, _contract(10))}) as url,
        pytest.raises(ContractFetchError, match="longer than 100 bytes"),
    ):
        contract_check.fetch_contract(url)


def test_an_answer_within_the_cap_is_read() -> None:
    routes = {
        "/api/v1/contract": (200, _contract(10)),
        "/api/v1/contract/database": (200, _database(10)),
    }
    with _serve(routes) as url:
        declared = contract_check.fetch_contract(url)
    assert declared.contract_version == 10


def test_cli_exits_2_when_the_pin_cannot_be_loaded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed ``_source.json`` is an error, not drift (exit 1 stays the drift code)."""
    cli = load_cli("check_view_contract")

    def broken_pin() -> SourceExpectation:
        raise ExpectationError("_source.json: schema_version_floor: must be a positive integer")

    monkeypatch.setattr(cli, "fetch_contract", lambda _url: _declared(10, 10))
    monkeypatch.setattr(cli, "load_source", broken_pin)
    monkeypatch.setattr(sys, "argv", ["check_view_contract.py", BASE])
    assert cli.main() == 2
    assert "error: _source.json" in capsys.readouterr().err
