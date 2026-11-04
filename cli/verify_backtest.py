#!/usr/bin/env python
"""Entry point: verify one stored backtest graph against its source database (T-280).

    uv run python cli/verify_backtest.py --graph urn:graph:derived:backtest:rule:P1:1 \\
        --db /path/to/rule_P1.db --label rule

Thin wrapper around :func:`projection.verify_backtest.main` (puts ``src/`` on ``sys.path``, like
``cli/project_backtest.py``); its docstring documents the read-only checks and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.verify_backtest import main

if __name__ == "__main__":
    sys.exit(main())
