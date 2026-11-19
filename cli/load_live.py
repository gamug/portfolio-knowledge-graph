#!/usr/bin/env python
"""Entry point: load one live day of SYSTEM_LIVE (Work item 47, T-940).

    uv run python cli/load_live.py --folder graph_export --day 2026-11-17
    uv run python cli/load_live.py --folder graph_export --day 2026-11-17 --check-store
    uv run python cli/load_live.py --folder graph_export --day 2026-11-17 --write

The command is thin: :func:`projection.load_live.main` owns the manifest adapter, the hashes, the
projection/SHACL reuse, the staging swap, the repository guard and the final JSON line. It never
writes to ``portfolio`` and never creates or deletes a repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.load_live import main

if __name__ == "__main__":
    sys.exit(main())
