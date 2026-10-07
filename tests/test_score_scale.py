"""``projection.score_scale``: upstream 0-100 strength -> [0, 1] risk ``:normalizedScore``."""

from decimal import Decimal

import pytest

from projection.score_scale import RESCALED_SCORE_TYPES, to_normalized_score


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [(0, Decimal(1)), (50, Decimal("0.5")), (100, Decimal(0))],
)
@pytest.mark.parametrize("score_type", ["VALORIZATION", "TECHNICAL"])
def test_bounds_and_midpoint_flip_polarity(
    score_type: str, upstream: int, expected: Decimal
) -> None:
    assert to_normalized_score(score_type, upstream) == expected


def test_decimal_exact_no_float_drift() -> None:
    # 1 - 0.333/100 as a float is 0.99667000...0001-ish; the Decimal path must be exact.
    assert to_normalized_score("TECHNICAL", 0.333) == Decimal("0.99667")
    assert to_normalized_score("TECHNICAL", Decimal("12.5")) == Decimal("0.875")


def test_none_passes_through() -> None:
    assert to_normalized_score("TECHNICAL", None) is None


@pytest.mark.parametrize("upstream", [-0.01, 100.01, float("nan"), float("inf"), float("-inf")])
def test_out_of_range_or_non_finite_is_an_error_not_clipped(upstream: float) -> None:
    with pytest.raises(ValueError, match="outside"):
        to_normalized_score("TECHNICAL", upstream)


@pytest.mark.parametrize("upstream", [True, False, "abc"])
def test_non_numeric_input_is_rejected(upstream: object) -> None:
    with pytest.raises(ValueError):
        # Deliberately ill-typed: this checks the runtime guard against values a DB row can
        # still deliver despite the annotation, so mypy's arg-type error is the point here.
        to_normalized_score("TECHNICAL", upstream)  # type: ignore[arg-type]


def test_fundamental_is_not_rescaled() -> None:
    # T-171 / SPEC D17: upstream rewrites FUNDAMENTAL's normalized_score in place every
    # cycle, so it must never become a :normalizedScore on an immutable ScoreSnapshot.
    # SHACL keeps it optional (legacy data), so this guard is the only enforcement.
    assert "FUNDAMENTAL" not in RESCALED_SCORE_TYPES
    with pytest.raises(ValueError, match="carries no normalizedScore"):
        to_normalized_score("FUNDAMENTAL", 50)


@pytest.mark.parametrize("score_type", ["SECTOR", "SEMANTIC", "UNKNOWN"])
def test_other_lanes_are_not_rescaled(score_type: str) -> None:
    with pytest.raises(ValueError, match="carries no normalizedScore"):
        to_normalized_score(score_type, 50)
