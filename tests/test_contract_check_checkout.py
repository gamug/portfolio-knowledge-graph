"""``projection.contract_check`` against a real ``portfolio-financial-analysis`` checkout.

Opt in with ``-m integration`` and ``PFA_CHECKOUT=<path to the checkout>``; add ``-s`` to see the
commit that was checked and any columns upstream added. Run it before every re-pin of
``view_contract.py`` and note the commit in the re-pin; nothing runs it for you (no CI,
constitution Code & Git #1).
"""

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from projection import contract_check

ENV_VAR = "PFA_CHECKOUT"


def checkout_from_env(env: Mapping[str, str]) -> Path:
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


def checkout_commit(path: Path) -> str:
    """The checkout's short ``HEAD`` sha, or ``unknown`` if it is not a git working tree."""
    try:
        out = subprocess.run(  # noqa: S603 -- fixed git command, the path is an argument
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


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


# --- the real checkout (opt in: -m integration) --------------------------------------------------


@pytest.mark.integration
def test_the_pin_matches_the_upstream_checkout() -> None:
    checkout = checkout_from_env(os.environ)
    commit = checkout_commit(checkout)
    report = contract_check.check(checkout)
    print(f"\nchecked {checkout} at commit {commit}")
    for note in report.notes:
        print(f"note: {note}")
    assert not report.drift, f"drift against commit {commit}:\n" + "\n".join(report.drift)
