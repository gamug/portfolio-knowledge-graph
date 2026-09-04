"""Provisional sentiment/category/severity formulas, isolated in one module.

**Everything here is a documented ASSUMPTION, not calibrated against ground
truth.** It is kept separate from the extraction code so the thresholds can be
tuned in one place once real calibration data exists. See ``etl/README.md``
("Provisional formulas requiring sign-off") for the full list.
"""

from __future__ import annotations

from etl.common.turtle_util import clamp

# --- G1: article_sentiment (positive, negative) -> ScoreSnapshot.rawValue ------
# Net polarity, clamped to the rawValue range [-1.0, 1.0].
_RAW_VALUE_LO = -1.0
_RAW_VALUE_HI = 1.0

# --- G2: article_category's 9 dimensions -> RiskEvent.category's 4-value enum ---
# (RiskEventShape sh:in: LEGAL | FINANCIAL | MARKET | NETWORK). The classifier's
# 10th possible label, 'other', has no entry on purpose: an article whose
# winning dimension is 'other' gets no RiskEvent at all, because none of the
# four categories can be honestly assigned.
CATEGORY_BUCKET = {
    "legal_regulatory": "LEGAL",
    "earnings_performance": "FINANCIAL",
    "capital_shareholder_returns": "FINANCIAL",
    "mergers_acquisitions": "FINANCIAL",
    "market_analyst_sentiment": "MARKET",
    "product_innovation": "MARKET",
    "partnerships_business_dev": "MARKET",
    "leadership_governance": "NETWORK",
    "labor_human_capital": "NETWORK",
}

# --- G3: severity has no source column -----------------------------------------
# Illustrative (not calibrated) keyword list for the "hard-trigger bump".
HARD_TRIGGER_KEYWORDS = (
    "lawsuit",
    "sec investigation",
    "investigation",
    "restatement",
    "material weakness",
    "class action",
    "subpoena",
    "indictment",
    "fraud",
    "settlement",
    "recall",
)

_SEVERITY_LADDER = ("LOW", "MODERATE", "HIGH", "CRITICAL")

# creation_gate bars: create a RiskEvent only if one of these signals clears.
GATE_NEGATIVE_MIN = 0.50
GATE_CATEGORY_SCORE_MIN = 0.70

# compute_severity tier boundaries.
_CRITICAL_NEGATIVE_MIN = 0.85
_CRITICAL_SCORE_MIN = 0.80
_CRITICAL_CATEGORIES = ("LEGAL", "FINANCIAL")
_HIGH_NEGATIVE_MIN = 0.70
_MODERATE_NEGATIVE_MIN = 0.50


def sentiment_raw_value(positive: float, negative: float) -> float:
    """G1: net polarity ``positive - negative``, clamped to ``[-1.0, 1.0]``."""
    return clamp(positive - negative, _RAW_VALUE_LO, _RAW_VALUE_HI)


def winning_category_and_score(label: str, score: float) -> tuple[str | None, float]:
    """Map the classifier's argmax ``label`` to a 4-value bucket.

    ``label``/``score`` are ``article_category``'s own argmax label and its
    confidence -- used directly rather than re-deriving "the winning dimension"
    from the nine dimension columns, since the classifier already did that.
    Returns ``(bucket_or_None, score)``; the bucket is ``None`` for ``'other'``
    or any unrecognised label (no honest 4-value mapping exists).
    """
    return CATEGORY_BUCKET.get(label), score


def creation_gate(negative: float, top_score: float) -> bool:
    """Return whether a ``:RiskEvent`` should be created for this article."""
    return negative >= GATE_NEGATIVE_MIN or top_score >= GATE_CATEGORY_SCORE_MIN


def compute_severity(negative: float, top_score: float, category: str, body_text: str) -> str:
    """Map ``(negative, top_score, category, body_text)`` to a severity tier.

    Proposed ladder, extended for one case the original ladder left
    unspecified: a RiskEvent created via the category-confidence path alone
    (``top_score >= GATE_CATEGORY_SCORE_MIN``) while ``negative`` is below every
    negative-based tier is mapped to ``LOW`` -- the lowest value in
    ``RiskEventShape``'s vocabulary, and the natural "some signal, but not the
    negative-tone signal" reading.
    """
    if (
        negative >= _CRITICAL_NEGATIVE_MIN
        and top_score >= _CRITICAL_SCORE_MIN
        and category in _CRITICAL_CATEGORIES
    ):
        tier = "CRITICAL"
    elif negative >= _HIGH_NEGATIVE_MIN:
        tier = "HIGH"
    elif negative >= _MODERATE_NEGATIVE_MIN:
        tier = "MODERATE"
    else:
        tier = "LOW"

    if body_text:
        lowered = body_text.lower()
        if any(kw in lowered for kw in HARD_TRIGGER_KEYWORDS):
            idx = min(_SEVERITY_LADDER.index(tier) + 1, len(_SEVERITY_LADDER) - 1)
            tier = _SEVERITY_LADDER[idx]
    return tier
