#!/usr/bin/env python
"""Entry point: load ``schema/`` into GraphDB and verify the result.

    python cli/load_schema.py [--dir path/to/schema]

Thin wrapper around :func:`kg_store.load_schema.main` (puts ``src/`` on ``sys.path``,
like ``cli/build_data_ttl.py``). Connection settings come from ``.env``
(``KG_HOST``, ``KG_REPOSITORY``, ``KG_USER``, ``KG_PASSWORD``); see ``docs/graphdb-setup.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kg_store.load_schema import main

if __name__ == "__main__":
    sys.exit(main())
