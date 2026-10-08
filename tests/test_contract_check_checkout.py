"""``projection.contract_check`` against a real ``portfolio-financial-analysis`` checkout.

Opt in with ``-m integration`` and ``PFA_CHECKOUT=<path to the checkout>`` (exported, or set in the
repo-root ``.env`` like the other paths, see ``.env.example``); add ``-s`` to see the
commit that was checked and any columns upstream added. Run it before every re-pin of
``view_contract.py`` and note the commit in the re-pin; nothing runs it for you (no CI,
constitution Code & Git #1).
"""

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest
from dotenv import dotenv_values

from projection import contract_check

ENV_VAR = "PFA_CHECKOUT"
REPO_ROOT = Path(__file__).resolve().parents[1]


def read_setting(env_file: Path, environ: Mapping[str, str]) -> dict[str, str | None]:
    """``environ`` over the repo-root ``.env``, for the one key only.

    An exported value wins (even an empty one, which reads as unset); a missing ``.env`` is fine.
    Only ``PFA_CHECKOUT`` is taken from the file, so the rest of it never enters the process.
    """
    from_file = dotenv_values(env_file).get(ENV_VAR) if env_file.is_file() else None
    exported = environ.get(ENV_VAR)
    return {ENV_VAR: exported if exported is not None else from_file}


def checkout_from_env(env: Mapping[str, str | None]) -> Path:
    """The checkout ``PFA_CHECKOUT`` names: skip when it is unset, fail when it is wrong.

    A path that is not a checkout must not skip: "1 skipped" reads as nothing to report, so a
    typo would let a re-pin go ahead without ever comparing anything.
    """
    value = env.get(ENV_VAR)
    if not value:
        pytest.skip(f"{ENV_VAR} is not set")
    path = Path(value)
    if not (path / "src" / "kg_schema").is_dir():
        pytest.fail(
            f"{ENV_VAR}={value} has no src/kg_schema: not a portfolio-financial-analysis checkout"
        )
    return path


def _git(path: Path, *args: str, isolated: bool = False) -> str:
    """Run git in ``path``. ``isolated`` ignores the machine's git configuration (throwaway repos)."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    out = subprocess.run(  # noqa: S603 -- fixed git command, the path is an argument
        ["git", "-C", str(path), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        env=env if isolated else None,
    )
    return out.stdout.strip()


def checkout_commit(path: Path) -> str:
    """The checkout's short ``HEAD`` sha, or ``unknown``.

    Uses the machine's own git configuration on purpose (it is a real checkout); only the
    throwaway repositories in the tests below are isolated from it.

    ``unknown`` when ``path`` is not itself the top of a git working tree: a folder inside some
    other repository would otherwise report that repository's commit.
    """
    try:
        if Path(_git(path, "rev-parse", "--show-toplevel")).resolve() != path.resolve():
            return "unknown"
        return _git(path, "rev-parse", "--short", "HEAD") or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# --- the rule that picks the checkout (hermetic) -------------------------------------------------


def test_an_unset_variable_skips() -> None:
    with pytest.raises(pytest.skip.Exception):
        checkout_from_env({})
    with pytest.raises(pytest.skip.Exception):
        checkout_from_env({ENV_VAR: ""})


def test_a_variable_that_is_not_a_checkout_fails_instead_of_skipping(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match="has no src/kg_schema"):
        checkout_from_env({ENV_VAR: str(tmp_path / "typo")})
    with pytest.raises(pytest.fail.Exception, match="has no src/kg_schema"):
        checkout_from_env({ENV_VAR: str(tmp_path)})


def test_a_file_is_not_a_checkout_either(tmp_path: Path) -> None:
    a_file = tmp_path / "kg_schema"
    a_file.write_text("x")
    with pytest.raises(pytest.fail.Exception, match="has no src/kg_schema"):
        checkout_from_env({ENV_VAR: str(a_file)})


def test_a_checkout_is_returned_as_given(tmp_path: Path) -> None:
    (tmp_path / "src" / "kg_schema").mkdir(parents=True)
    assert checkout_from_env({ENV_VAR: str(tmp_path)}) == tmp_path


# --- where the variable comes from: the environment over .env (hermetic) --------------------------


def test_a_value_in_dot_env_is_used_when_nothing_is_exported(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"OTHER=1\n{ENV_VAR}=/some/checkout\n")
    assert read_setting(env_file, {}) == {ENV_VAR: "/some/checkout"}


def test_an_exported_value_beats_dot_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{ENV_VAR}=/from/file\n")
    assert read_setting(env_file, {ENV_VAR: "/exported"}) == {ENV_VAR: "/exported"}


def test_an_empty_or_valueless_setting_reads_as_unset_and_skips(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{ENV_VAR}\n")  # a line with no value
    with pytest.raises(pytest.skip.Exception):
        checkout_from_env(read_setting(env_file, {}))
    env_file.write_text(f"{ENV_VAR}=/from/file\n")
    with pytest.raises(pytest.skip.Exception):  # exported empty: the shell said "unset" on purpose
        checkout_from_env(read_setting(env_file, {ENV_VAR: ""}))


def test_a_missing_dot_env_is_fine(tmp_path: Path) -> None:
    assert read_setting(tmp_path / ".env", {}) == {ENV_VAR: None}
    assert read_setting(tmp_path / ".env", {ENV_VAR: "/x"}) == {ENV_VAR: "/x"}


def test_the_rest_of_dot_env_is_not_returned(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"SQL_FINANCIAL_DB=/secret.db\n{ENV_VAR}=/c\n")
    assert set(read_setting(env_file, {})) == {ENV_VAR}


def test_the_commit_is_unknown_outside_a_git_tree(tmp_path: Path) -> None:
    assert checkout_commit(tmp_path / "missing") == "unknown"


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _commit_in(repo: Path) -> str:
    """A repository with one commit, whatever the machine's git signing, hooks or defaults say."""
    _git(repo, "init", "-q", isolated=True)
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "f.txt", isolated=True)
    _git(
        repo,
        "-c", "user.name=t",
        "-c", "user.email=t@t",
        "-c", "commit.gpgsign=false",
        "-c", f"core.hooksPath={os.devnull}",
        "commit", "-q", "-m", "m",
        isolated=True,
    )  # fmt: skip
    return _git(repo, "rev-parse", "--short", "HEAD", isolated=True)


@needs_git
def test_the_commit_is_the_checkouts_head(tmp_path: Path) -> None:
    assert checkout_commit(tmp_path) == "unknown"  # not a repository yet
    head = _commit_in(tmp_path)
    assert checkout_commit(tmp_path) == head


@needs_git
def test_a_folder_inside_another_repository_is_not_given_its_commit(tmp_path: Path) -> None:
    _commit_in(tmp_path)
    inner = tmp_path / "inner"
    inner.mkdir()
    assert checkout_commit(inner) == "unknown"


# --- the real checkout (opt in: -m integration) --------------------------------------------------


@pytest.mark.integration
def test_the_pin_matches_the_upstream_checkout() -> None:
    checkout = checkout_from_env(read_setting(REPO_ROOT / ".env", os.environ))
    commit = checkout_commit(checkout)
    report = contract_check.check(checkout)
    print(f"\nchecked {checkout} at commit {commit}")
    for note in report.notes:
        print(f"note: {note}")
    assert not report.drift, f"drift against commit {commit}:\n" + "\n".join(report.drift)
