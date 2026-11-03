#!/usr/bin/env python
"""Entry point: check ``schema/fibo_terms.csv`` against the pinned FIBO release (T-210).

    uv run python cli/check_fibo_terms.py --zip PATH --terms schema/fibo_terms.csv

Thin wrapper around :func:`projection.fibo_terms.main` (puts ``src/`` on ``sys.path``, like the
other entrypoints); its docstring documents the sha256 pin and the exit status (0 all terms pass,
1 a check failure, 2 a bad argument). The zip is not committed: this is the opt-in real-release
check, not a hermetic test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection.fibo_terms import main

if __name__ == "__main__":
    sys.exit(main())
