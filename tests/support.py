"""Plain helpers shared by test modules (the fixtures are in ``conftest.py``): the worked example
of ``schema/instances.trig`` as the stored context its batches are checked beside."""

from __future__ import annotations

from pathlib import Path

import rdflib

from kg_store.gate import load_gate_schema, references

SCHEMA = Path(__file__).resolve().parent.parent / "schema"


def instance_graphs() -> dict[str, rdflib.Graph]:
    """``schema/instances.trig``'s named graphs, by name (the worked example)."""
    ds = rdflib.Dataset(default_union=False)
    ds.parse(SCHEMA / "instances.trig", format="trig")
    return {str(g.identifier): g for g in ds.graphs() if len(g)}


def context_for(name: str) -> rdflib.Graph:
    """What the rest of the worked example says about the individuals graph ``name`` points at,
    as the store would hold it once the other graphs are loaded (T-146)."""
    graphs = instance_graphs()
    refs = references(graphs[name], load_gate_schema(SCHEMA.resolve()))
    # The Assets are typed in reference.ttl; the other graphs hold the Portfolios.
    others = {k: g for k, g in graphs.items() if k != name}
    others["urn:graph:reference"] = rdflib.Graph().parse(SCHEMA / "reference.ttl", format="turtle")
    context = rdflib.Graph()
    for graph in others.values():
        for ref in refs:
            for p, o in graph.predicate_objects(ref):
                context.add((ref, p, o))
    return context
