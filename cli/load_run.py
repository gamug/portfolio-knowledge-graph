#!/usr/bin/env python
"""Entry point: load one labelled backtest delivery and prove it in one command (Work items 29, 31, 35).

    uv run python cli/load_run.py --label final --dir /path/to/delivery [--check-store] [--write]
        [--to-production] [--windows P1,H1] [--min-free-pct 8]
    uv run python cli/load_run.py --label rule --dir /path/to/pilot --no-manifest --no-config

Thin wrapper around :func:`projection.load_run.main` (puts ``src/`` on ``sys.path``, like
``cli/project_backtest.py``); its docstring documents the delivery discovery, the manifest and
configuration checks, the chronological window order, the read-only pre-flight, the metadata graph,
the final table, the one-graph rollback commands and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.load_run import main

if __name__ == "__main__":
    sys.exit(main())
