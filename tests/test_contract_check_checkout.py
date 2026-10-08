"""``projection.contract_check`` against a real ``portfolio-financial-analysis`` checkout.

Opt in with ``-m integration`` and ``PFA_CHECKOUT=<path to the checkout>``. Run it before every
re-pin of ``view_contract.py``; nothing runs it for you (no CI, constitution Code & Git #1).
"""

import os
from pathlib import Path

import pytest

from projection import contract_check


@pytest.mark.integration
def test_the_pin_matches_the_upstream_checkout() -> None:
    checkout = os.environ.get("PFA_CHECKOUT")
    if not checkout or not (Path(checkout) / "src" / "kg_schema").is_dir():
        pytest.skip("PFA_CHECKOUT is not set to a portfolio-financial-analysis checkout")
    report = contract_check.check(Path(checkout))
    assert not report.drift, "\n".join(report.drift)
