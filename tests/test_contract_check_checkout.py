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


def test_a_checkout_is_returned_as_given(tmp_path: Path) -> None:
    (tmp_path / "src" / "kg_schema").mkdir(parents=True)
    assert checkout_from_env({ENV_VAR: str(tmp_path)}) == tmp_path


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
    # An exported value wins; the repo-root .env is read for this one key only, so the rest of it
    # does not leak into the process environment.
    env = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}
    checkout = checkout_from_env(env)
    commit = checkout_commit(checkout)
    report = contract_check.check(checkout)
    print(f"\nchecked {checkout} at commit {commit}")
    for note in report.notes:
        print(f"note: {note}")
    assert not report.drift, f"drift against commit {commit}:\n" + "\n".join(report.drift)
