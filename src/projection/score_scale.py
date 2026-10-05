"""Upstream ``score_snapshot.normalized_score`` (0-100) -> ``:normalizedScore`` ([0, 1]).

Two conventions differ (T-030, ``SPEC.md`` D12 / §2.6):

* **Scale.** Upstream (``portfolio-financial-analysis``, ``cycle.scores.normalize``)
  writes a 0-100 point score, 50 = cohort average. ``ScoreSnapshotShape`` bounds
  ``normalizedScore`` to [0.0, 1.0].
* **Polarity.** Upstream's is a *strength* score (higher = better; FUNDAMENTAL is
  "higher = fundamentally stronger"). Every ``normalizedScore`` here is a *risk*
  reading (0 = no risk, 1 = critical; ``docs/06-ontology-definition.md`` §1.8), and the
  attractiveness formula inverts risk inputs via ``WeightComponent.inverted``.

The projection therefore writes ``1 - score / 100``, so the graph keeps one polarity for
every agent lane. The upstream value is not lost: the caller also writes it as
``:rawValue`` (0-100).

This applies to the FUNDAMENTAL, VALORIZATION, TECHNICAL, SECTOR and SEMANTIC
``score_type``s only; ``Sentiment`` and ``SectorRelativeMomentum`` compare on ``rawValue``
and carry no ``normalizedScore``.
"""

from __future__ import annotations

from decimal import Decimal

UPSTREAM_MIN = Decimal(0)
UPSTREAM_MAX = Decimal(100)


def to_normalized_score(upstream: float | Decimal | None) -> Decimal | None:
    """Return the ``:normalizedScore`` for an upstream 0-100 strength score.

    ``None`` in -> ``None`` out (upstream leaves ``normalized_score`` NULL until the
    cohort is normalized). A value outside [0, 100] raises ``ValueError``: upstream clamps,
    so one means the contract drifted and must not be silently clipped into the graph.
    """
    if upstream is None:
        return None
    value = Decimal(str(upstream))
    if not UPSTREAM_MIN <= value <= UPSTREAM_MAX:
        raise ValueError(f"upstream normalized_score {upstream!r} outside [0, 100]")
    return (UPSTREAM_MAX - value) / UPSTREAM_MAX
