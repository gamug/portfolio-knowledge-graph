#!/usr/bin/env python
"""Entry point: run the T-025 acceptance checks against the configured GraphDB.

    python cli/verify_store.py

Exit status is 0 when all three pass, 1 otherwise. See ``kg_store.acceptance``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kg_store.acceptance import CHECKS
from kg_store.graphdb import GraphDB, GraphDBError


def main() -> int:
    try:
        db = GraphDB.from_env()
    except GraphDBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    failed = 0
    for name, check in CHECKS:
        try:
            print(f"PASS  {name}: {check(db)}")
        except (AssertionError, GraphDBError) as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
