"""Fail if upstream's ``v_*`` views drifted from the pinned read contract (T-030, T-173).

uv run python cli/check_view_contract.py PATH/TO/portfolio-financial-analysis
uv run python cli/check_view_contract.py http://HOST:PORT/api/v1

A path builds upstream's views from a checkout. A URL reads the running service's
``GET /contract`` (and ``/contract/database`` if it offers it) and also checks the versions: the
declared ``contract_version`` must equal the pin's, and the database's ``schema_version`` must
not be below the pin's floor. Exit status: 0 no drift, 1 drift, 2 the service could not be read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.contract_check import (
    ContractFetchError,
    ContractReport,
    check,
    check_service,
    fetch_contract,
)
from projection.expectations import load_source


def _report(target: str) -> ContractReport:
    if target.startswith(("http://", "https://")):
        declared = fetch_contract(target)
        print(
            f"service: contract_version {declared.contract_version}, code {declared.code_version}"
        )
        if declared.database is not None:
            print(f"service database: schema_version {declared.database.schema_version}")
        return check_service(declared, load_source())
    return check(Path(target))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "upstream", help="checkout of portfolio-financial-analysis, or its API URL (…/api/v1)"
    )
    try:
        report = _report(parser.parse_args().upstream)
    except ContractFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
