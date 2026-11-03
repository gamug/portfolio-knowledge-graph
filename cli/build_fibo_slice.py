#!/usr/bin/env python
"""Entry point: build ``schema/fibo.ttl`` from the pinned FIBO release (T-211, brief §4.2).

    uv run python cli/build_fibo_slice.py --zip PATH --terms schema/fibo_terms.csv \
        --out schema/fibo.ttl

Thin wrapper around :func:`projection.fibo_slice.main` (puts ``src/`` on ``sys.path``, like the
other entrypoints); its docstring documents the sha256 pin and the exit status (0 written, 1 a
check failure, 2 a bad argument). The zip is not committed: the committed slice is what the
hermetic tests read, and this command is how a new release rebuilds it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.fibo_slice import main

if __name__ == "__main__":
    sys.exit(main())
