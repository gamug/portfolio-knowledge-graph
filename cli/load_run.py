#!/usr/bin/env python
"""Entry point: load one labelled backtest family and prove it in one command (Work item 29).

    uv run python cli/load_run.py --label rule --dir /path/to/runs [--write] [--to-production]

Thin wrapper around :func:`projection.load_run.main` (puts ``src/`` on ``sys.path``, like
``cli/project_backtest.py``); its docstring documents the ordered stages, the final table, the
one-graph rollback commands and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.load_run import main

if __name__ == "__main__":
    sys.exit(main())
