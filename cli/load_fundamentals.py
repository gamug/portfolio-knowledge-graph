#!/usr/bin/env python
"""Entry point: load the fundamentals block C delivery (Work item 45, T-813-T-815).

    uv run python cli/load_fundamentals.py --dir "/path/to/bloque_c_fundamentales"
    uv run python cli/load_fundamentals.py --dir "/path/to/bloque_c_fundamentales" --check-store
    uv run python cli/load_fundamentals.py --dir "/path/to/bloque_c_fundamentales" --write --to-production

Thin wrapper around :func:`projection.fundamentals.main` (puts ``src/`` on ``sys.path``, like
``cli/load_mv_base.py``); its docstring documents the manifest and mask checks, the append-only
fundamentals graph, the read-only pre-flight and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.fundamentals import main

if __name__ == "__main__":
    sys.exit(main())
