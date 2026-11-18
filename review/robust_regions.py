from collections.abc import Iterator
from fractions import Fraction

from calibration.evidence import FrozenEvidence
from review.region_set import CandidateSet, ClosedRegion, Endpoint
from review.robust_comparison import combined_breakpoints, qualifying_votes


def _open_cells(points: tuple[Fraction, ...]) -> Iterator[tuple[Endpoint, Endpoint, Fraction]]:
    if not points:
        yield None, None, Fraction(0)
        return

    yield None, points[0], points[0] - 1
    for lower, upper in zip(points, points[1:]):
        yield lower, upper, (lower + upper) / 2
    yield points[-1], None, points[-1] + 1


def find_robust_candidate_set(
    evidences: tuple[FrozenEvidence, ...], k: int, q: int
) -> CandidateSet:
    """Candidates where at least q named scenarios each reach k qualifying specimens.

    Each scenario counts the shared target once plus retained originals whose
    absolute residual is at least the target's, so all comparisons are affine
    and the vote total is constant on each open cell between breakpoints.
    """
    points = combined_breakpoints(evidences)
    accepted_points = {
        point for point in points
        if qualifying_votes(evidences, point, k) >= q
    }
    pieces = [ClosedRegion(point, point) for point in accepted_points]
    for lower, upper, witness in _open_cells(points):
        if qualifying_votes(evidences, witness, k) < q:
            continue
        lower_accepted = lower is None or lower in accepted_points
        upper_accepted = upper is None or upper in accepted_points
        if lower_accepted and upper_accepted:
            pieces.append(ClosedRegion(lower, upper))
    return CandidateSet(tuple(pieces))
