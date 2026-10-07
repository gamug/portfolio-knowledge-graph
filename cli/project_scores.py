#!/usr/bin/env python
"""Entry point: project ``v_score_snapshot`` into dated ``ingest`` graphs (T-031).

    uv run python cli/project_scores.py [--write] [--late-keys PATH] [--run-day YYYY-MM-DD] [--replay]

Thin wrapper around :func:`projection.project_scores.main` (puts ``src/`` on ``sys.path``,
like ``cli/load_schema.py``); its docstring documents the arguments, the run-day and replay
rules, the key files and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.project_scores import main

if __name__ == "__main__":
    sys.exit(main())
