#!/usr/bin/env python
"""Entry point: validate a Turtle batch against the SHACL shapes and write it to the store.

    python cli/ingest.py batch.ttl --graph urn:graph:ingest:SEMANTIC:2026-08-06
    python cli/ingest.py batch.ttl --graph urn:graph:ingest:SEMANTIC:2026-08-06 --check

``--check`` validates without touching the store. Exit status is 0 when the batch was
accepted (or would be), 2 when it was rejected, 1 on any other error. See
``kg_store.gate`` for what is checked.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kg_store.gate import IngestRejected, check_target, ingest, parse_batch, validate
from kg_store.graphdb import GraphDB, GraphDBError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path, help="Turtle file holding the batch")
    parser.add_argument("--graph", required=True, help="target named graph IRI")
    parser.add_argument("--check", action="store_true", help="validate only; do not write")
    args = parser.parse_args(argv)
    try:
        data = args.file.read_bytes()
        if args.check:
            check_target(args.graph)
            batch = parse_batch(data)
            validate(batch)
            print(f"accepted (check only): {len(batch)} triples for {args.graph}")
        else:
            n = ingest(GraphDB.from_env(), data, args.graph)
            print(f"written: {n} triples to {args.graph}")
    except IngestRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    except (GraphDBError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
