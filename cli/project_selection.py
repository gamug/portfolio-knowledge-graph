#!/usr/bin/env python
"""Entry point: project the six backtest selection views into one sibling graph per run (Work item 26).

    uv run python cli/project_selection.py --db LABEL=PATH [--db LABEL=PATH ...] [--write] [--to-production]

Thin wrapper around :func:`projection.project_selection.main` (puts ``src/`` on ``sys.path``,
like ``cli/project_backtest.py``); its docstring documents the run label, the production guard and
the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.project_selection import main

if __name__ == "__main__":
    sys.exit(main())
