"""Upstream ``score_snapshot.normalized_score`` (0-100) -> ``:normalizedScore`` ([0, 1]).

Two conventions differ (T-030, ``SPEC.md`` §2.6; ``schema/README.md`` refinement 6):

* **Scale.** Upstream (``portfolio-financial-analysis``, ``cycle.scores.normalize``)
  writes a 0-100 point score, 50 = cohort average. ``ScoreSnapshotShape`` bounds
  ``normalizedScore`` to [0.0, 1.0].
* **Polarity.** Upstream's is a *strength* score (higher = better; FUNDAMENTAL is
  "higher = fundamentally stronger"). Every ``normalizedScore`` here is a *risk*
  reading (0 = no risk, 1 = critical; ``docs/06-ontology-definition.md`` §1.8), and the
  attractiveness formula inverts risk inputs via ``WeightComponent.inverted``.

The projection therefore writes ``1 - normalized_score / 100``, so the graph keeps one
polarity for every lane that carries a ``normalizedScore``. Upstream's separate
``raw_value`` column (the score before cross-sectional normalization) is what maps to
``:rawValue``; its range per ``score_type`` is decided with the write path (T-031).

The same conversion applies to ``v_sector_aggregate_snapshot.mean_normalized`` (the mean of
a sector's members' TECHNICAL ``normalized_score``, so the same 0-100 strength reading), which
becomes a ``:SectorAggregateSnapshot``'s ``normalizedScore``: call
``to_normalized_score("TECHNICAL", mean_normalized)``. The map is linear, so flipping the mean
equals the mean of the flipped scores.

Only the three lanes in :data:`RESCALED_SCORE_TYPES` are converted. Upstream ``SECTOR``
is ``SectorRelativeMomentum`` (``SPEC.md`` D6) and SEMANTIC snapshots are ``Sentiment``
(FR-005): both compare on a ``rawValue`` that ``ScoreSnapshotShape`` bounds to [-1, 1]
(T-081, T-140) and carry no ``normalizedScore``, so mapping upstream's values into that
range is open, also for T-031.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

UPSTREAM_MIN = Decimal(0)
UPSTREAM_MAX = Decimal(100)

# score_type (= agentOrigin) -> metricType, for the lanes whose normalized_score is projected.
RESCALED_SCORE_TYPES: dict[str, str] = {
    "FUNDAMENTAL": "ScoreFinanciero",
    "VALORIZATION": "ScoreCuantitativo",
    "TECHNICAL": "ScoreTecnico",
}


def to_normalized_score(score_type: str, upstream: float | Decimal | None) -> Decimal | None:
    """Return the ``:normalizedScore`` for an upstream 0-100 strength score of *score_type*.

    ``None`` in -> ``None`` out (upstream leaves ``normalized_score`` NULL until the
    cohort is normalized). Raises ``ValueError`` for a ``score_type`` outside
    :data:`RESCALED_SCORE_TYPES`, and for a non-finite value or one outside [0, 100]:
    upstream clamps, so either means the contract drifted and must not be silently
    clipped into the graph.
    """
    if score_type not in RESCALED_SCORE_TYPES:
        raise ValueError(f"score_type {score_type!r} carries no normalizedScore here")
    if upstream is None:
        return None
    try:
        value = Decimal(str(upstream))
    except InvalidOperation as exc:
        raise ValueError(f"upstream normalized_score {upstream!r} is not a number") from exc
    if not value.is_finite() or not UPSTREAM_MIN <= value <= UPSTREAM_MAX:
        raise ValueError(f"upstream normalized_score {upstream!r} outside [0, 100]")
    return (UPSTREAM_MAX - value) / UPSTREAM_MAX
