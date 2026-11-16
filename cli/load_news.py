#!/usr/bin/env python
"""Entry point: load the block D news rows into year graphs (Work item 46).

    uv run python cli/load_news.py --label final --dir "/path/to/2026-11-17_final"
    uv run python cli/load_news.py --label final --dir "..." --check-store
    uv run python cli/load_news.py --label final --dir "..." --write --to-production

Thin wrapper around :func:`projection.news.main` (puts ``src/`` on ``sys.path``, like
``cli/load_series.py``); its docstring documents the manifest and SHA256SUMS verification, the
year-split append-only graphs, the read-only pre-flight and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.news import main

if __name__ == "__main__":
    sys.exit(main())
