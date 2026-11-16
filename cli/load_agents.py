#!/usr/bin/env python
"""Entry point: load the block F manager/narrator/news/bull-mode files (Work item 46, T-900-T-909).

    uv run python cli/load_agents.py --label final
    uv run python cli/load_agents.py --label final --check-store
    uv run python cli/load_agents.py --label final --write --to-production

Thin wrapper around :func:`projection.agents.main` (puts ``src/`` on ``sys.path``, like
``cli/load_series.py``); its docstring documents the four append-only graphs, the hash checks,
the dry run and the graph-in-doubt handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.agents import main

if __name__ == "__main__":
    sys.exit(main())
