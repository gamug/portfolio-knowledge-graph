#!/usr/bin/env python
"""Entry point: load one upstream aggregates file after the run loader (Work item 37).

    uv run python cli/load_aggregates.py --label candidate --dir /path/to/candidate_y2
        [--check-store | --write] [--to-production]

Thin wrapper around :func:`projection.load_aggregates.main` (puts ``src/`` on ``sys.path``, like
``cli/load_run.py``); its docstring documents the dry run, the read-only pre-flight, the manifest
check, the stored-row verification and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.load_aggregates import main

if __name__ == "__main__":
    sys.exit(main())
