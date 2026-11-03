#!/usr/bin/env python
"""Entry point: load the asset master (universe.db) into a universe quarter graph (T-220).

    uv run python cli/load_universe.py [--since YYYY-MM-DD] [--as-of YYYY-MM-DD]
    uv run python cli/load_universe.py --write [--to-production]

Thin wrapper around :func:`kg_store.universe.main` (puts ``src/`` on ``sys.path``, like
``cli/ingest.py``). It reads ``SQL_UNIVERSE_DB``, builds the ``:Universe``/``:Asset``/
``:UniverseMembership`` batch and, by default, SHACL-validates it without contacting the store;
``--write`` appends it through the ingest gate. The target graph is
``urn:graph:universe:{year}-Q{n}`` for ``--as-of``; the production repository also needs
``--to-production``. Its docstring documents the ``--since`` filter, the exit status and the
one-load-per-repository limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kg_store.universe import main

if __name__ == "__main__":
    sys.exit(main())
