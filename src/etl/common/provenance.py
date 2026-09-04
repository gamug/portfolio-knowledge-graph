"""``provenanceId`` formatting -- one place.

Only the ``articles:<id>`` form is implemented for this phase.
``discovered_urls:<id>`` and the EDGAR accession-number form are out of scope
(no SEC data is populated yet -- see ``10-integration-roadmap.md``).
"""

from __future__ import annotations


def article_provenance_id(article_id: int) -> str:
    """Return the ``provenanceId`` string for an ``articles`` row."""
    return f"articles:{article_id}"
