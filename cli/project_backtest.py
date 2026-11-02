#!/usr/bin/env python
"""Entry point: project the eight m018 backtest/GUARD views into one graph per run (T-207).

    uv run python cli/project_backtest.py --db PATH [--db PATH ...] [--write] [--to-production]

Thin wrapper around :func:`projection.project_backtest.main` (puts ``src/`` on ``sys.path``,
like ``cli/project_scores.py``); its docstring documents the production guard and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.project_backtest import main

if __name__ == "__main__":
    sys.exit(main())
