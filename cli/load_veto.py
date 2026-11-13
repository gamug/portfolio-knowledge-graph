#!/usr/bin/env python
"""Entry point: load the final Veto Hierarchy delivery from its manifest (Work item 46, T-866).

    uv run python cli/load_veto.py --manifest manifest_final.json
    uv run python cli/load_veto.py --manifest manifest_final.json --check-store
    uv run python cli/load_veto.py --manifest manifest_final.json --write --to-production

The command is thin: :func:`projection.load_veto.main` owns the manifest, SHA-256, filters,
projection, SHACL and gate sequence. A dry run contacts no store; ``--check-store`` only plans;
``--write`` refuses a non-empty graph and never deletes. A draft manifest can be dry-run or
written only to a scratch repository; production needs a final manifest and ``--to-production``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.load_veto import main

if __name__ == "__main__":
    sys.exit(main())
