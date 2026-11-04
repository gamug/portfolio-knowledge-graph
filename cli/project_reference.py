#!/usr/bin/env python
"""Entry point: project ticker history and the orchestrator views (T-354).

    uv run python cli/project_reference.py --db LABEL=PATH [--db LABEL=PATH ...] \
        [--as-of YYYY-MM-DD] [--write] [--to-production]

Thin wrapper around :func:`projection.project_reference.main` (puts ``src/`` on ``sys.path``,
like ``cli/project_backtest.py``); its docstring documents the label, the snapshot date, the
production guard and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.project_reference import main

if __name__ == "__main__":
    sys.exit(main())
