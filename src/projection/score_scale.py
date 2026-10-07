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

FUNDAMENTAL is deliberately not converted (T-171, ``SPEC.md`` D17): upstream rewrites a
FUNDAMENTAL row's ``normalized_score`` in place on every cycle that re-normalizes the filing,
so it cannot sit on an immutable ``ScoreSnapshot``. A FUNDAMENTAL snapshot carries
``:rawValue`` instead; the per-cycle value is ``v_cycle_ranking_component.component_value``,
read as ``:componentValue`` (T-155).

Only the lanes in :data:`RESCALED_SCORE_TYPES` are converted. Upstream ``SECTOR``
is ``SectorRelativeMomentum`` (``SPEC.md`` D6) and SEMANTIC snapshots are ``Sentiment``
(FR-005): both compare on a ``rawValue`` and do not require a ``normalizedScore``. The shape
bounds ``Sentiment``'s to [-1, 1] (T-081) and SECTOR's to [-100, 100] (T-140, widened by
T-155: upstream's TECHNICAL points, read verbatim), so only SEMANTIC's mapping into its range
is open, for T-031. SECTOR's 0-100 ``normalized_score`` becomes an optional
``normalizedScore`` (T-155), converted like the other two lanes (SECTOR joined
:data:`RESCALED_SCORE_TYPES` with the write path, T-031). SEMANTIC's is not projected.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

UPSTREAM_MIN = Decimal(0)
UPSTREAM_MAX = Decimal(100)

# score_type (= agentOrigin) -> metricType, for the lanes whose normalized_score is projected.
RESCALED_SCORE_TYPES: dict[str, str] = {
    "VALORIZATION": "ScoreCuantitativo",
    "TECHNICAL": "ScoreTecnico",
    "SECTOR": "SectorRelativeMomentum",
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
