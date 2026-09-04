#!/usr/bin/env python
"""Entry point: build ``data.ttl`` from Wikipedia + urls.db/nlp.db.

    python cli/build_data_ttl.py              # full run
    python cli/build_data_ttl.py --limit 500  # smoke test (caps news rows)

Thin wrapper around :func:`etl.build_data_ttl.main` -- bootstraps ``src/`` onto
``sys.path`` (mirroring the sibling Portfolio Thesis repos' ``cli/*.py``
entrypoints, e.g. ``portfolio-data-mining``'s ``cli/pricing_cli.py``) so this
runs standalone with no ``PYTHONPATH`` setup. See ``src/etl/README.md`` for
what the build actually does and how it's configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from etl.build_data_ttl import main

if __name__ == "__main__":
    main()
