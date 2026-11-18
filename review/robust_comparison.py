from fractions import Fraction

from calibration.evidence import FrozenEvidence
from review.comparison import comparison_breakpoints, count_qualifying_specimens


def qualifying_votes(evidences: tuple[FrozenEvidence, ...], candidate: Fraction, k: int) -> int:
    """How many named scenarios independently reach k specimens at this candidate."""
    return sum(
        count_qualifying_specimens(evidence, candidate) >= k for evidence in evidences
    )


def combined_breakpoints(evidences: tuple[FrozenEvidence, ...]) -> tuple[Fraction, ...]:
    """Every candidate where any group's signed residual match can change a count."""
    points = set()
    for evidence in evidences:
        points.update(comparison_breakpoints(evidence))
    return tuple(sorted(points))
