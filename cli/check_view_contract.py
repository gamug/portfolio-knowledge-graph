"""Fail if upstream's ``v_*`` views drifted from the pinned read contract (T-030).

uv run python cli/check_view_contract.py PATH/TO/portfolio-financial-analysis
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.contract_check import check


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("upstream", type=Path, help="checkout of portfolio-financial-analysis")
    report = check(parser.parse_args().upstream)
    for line in report.notes:
        print(f"NOTE  {line}")
    for line in report.drift:
        print(f"DRIFT {line}")
    print(
        "view contract: OK" if not report.drift else f"view contract: {len(report.drift)} drift(s)"
    )
    return 1 if report.drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
