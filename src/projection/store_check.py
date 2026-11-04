"""Read-only ``--check-store``: validate a projected batch beside the live store's context.

The dry run validates beside a local rules graph and the universe database. The ingest gate, on a
write, instead fetches from the store only the properties the shapes read for the individuals a
batch points at (``gate.fetch_context``). A missing ``sh:class``/range can therefore make a dry run
pass and the first real write fail. This module performs the same fetch with ``SELECT`` only and
runs the gate's validation, so the operator can see that before writing. It never writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from kg_store import gate
from kg_store.graphdb import GraphDB


def check_graphs(
    store: GraphDB,
    graphs: Mapping[str, bytes],
    directory: Path | None = None,
    *,
    label: str,
) -> bool:
    """Validate each graph's batch beside the store's context; return True if any is refused."""
    print(f"\n{label}")
    if not graphs:
        print("  nothing to check")
        return False
    failed = False
    for graph in sorted(graphs):
        batch = gate.parse_batch(graphs[graph])
        try:
            gate.validate_against_store(store, batch, directory)
        except gate.IngestRejected as exc:
            print(f"  would be refused: {graph}\n{exc}")
            failed = True
        else:
            print(f"  would be accepted: {graph}")
    return failed
