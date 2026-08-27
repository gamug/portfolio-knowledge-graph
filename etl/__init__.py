"""KG-population ETL for the portfolio knowledge graph.

Turns the external ``news-collector``/``news-crawler`` SQLite database
(``urls.db``) plus the live Wikipedia S&P 500 constituent table into a flat
Turtle ``data.ttl`` that loads on top of this repo's ``schema/`` files
(``tbox.ttl`` -> ``shapes.ttl`` -> ``reference.ttl`` -> ``rules.ttl`` ->
``data.ttl``).

This is roadmap step 1 of ``10-integration-roadmap.md`` (step 0, ``schema/``,
being the only step previously marked done). It is an MVP single-shot load, not
the named-graph-partitioned target architecture of ``07-ontology-topology.md``.

Run it with::

    python -m etl.build_data_ttl            # full run -> data.ttl
    python -m etl.build_data_ttl --limit 500  # smoke test

Configuration (DB path, schema dir, output path, source URL) is resolved by
:mod:`etl.config` from a repo-root ``.env`` file; see ``.env.example``.
"""
