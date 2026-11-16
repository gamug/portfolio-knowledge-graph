#!/usr/bin/env python
"""Entry point: load the block E daily series (SPY and MARKOWITZ_MV).

    uv run python cli/load_series.py --label final --dir "/path/to/series_diarias_referencia"
    uv run python cli/load_series.py --label final --dir "..." --check-store
    uv run python cli/load_series.py --label final --dir "..." --write --to-production

Thin wrapper around :func:`projection.series.main` (puts ``src/`` on ``sys.path``, like
``cli/load_mv_base.py``); its docstring documents the manifest verification, the two append-only
series graphs, the read-only pre-flight and the exit status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.series import main

if __name__ == "__main__":
    sys.exit(main())
