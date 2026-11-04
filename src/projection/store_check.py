"""Read-only ``--check-store``: run the real gate's plan for a projected batch.

The dry run validates beside a local rules graph and the universe database. The ingest gate, on a
write, instead fetches from the store only the properties the shapes read for the individuals a
batch points at (``gate.fetch_context``), then applies the graph-existence (check 2), stored
individual (check 6) and closing-state (check 7) checks. A dry run cannot see any of those. This
module calls the same ``gate.plan`` the real write uses, with ``SELECT`` only, and reports each
graph as would-be-written, already-in-the-store (skipped) or refused. It never writes.
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
        try:
            plan = gate.plan(store, graphs[graph], graph, directory)
        except gate.IngestRejected as exc:
            print(f"  refused: {graph}\n{exc}")
            failed = True
        else:
            print(f"  {plan.status.value}: {graph}")
    return failed
