#!/usr/bin/env python
"""Entry point: load the external mean-variance base Markowitz delivery (Work item 44).

    uv run python cli/load_mv_base.py --label final --dir "/path/to/mv_base"
    uv run python cli/load_mv_base.py --label final --dir "/path/to/mv_base" --check-store
    uv run python cli/load_mv_base.py --label final --dir "/path/to/mv_base" --write --to-production

Thin wrapper around :func:`projection.mv_base.main` (puts ``src/`` on ``sys.path``, like
``cli/load_aggregates.py``); its docstring documents the manifest checks, the external graph,
the read-only pre-flight and the exit status. The ``provenance/`` folder is not required.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.mv_base import main

if __name__ == "__main__":
    sys.exit(main())
