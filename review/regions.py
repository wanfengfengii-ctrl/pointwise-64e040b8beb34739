from collections.abc import Iterator
from fractions import Fraction

from review.comparison import comparison_breakpoints, count_qualifying_specimens
from review.region_set import CandidateSet, ClosedRegion, Endpoint
from review.request import IssueRequest


def _open_cells(points: tuple[Fraction, ...]) -> Iterator[tuple[Endpoint, Endpoint, Fraction]]:
    if not points:
        yield None, None, Fraction(0)
        return

    yield None, points[0], points[0] - 1
    for lower, upper in zip(points, points[1:]):
        yield lower, upper, (lower + upper) / 2
    yield points[-1], None, points[-1] + 1


def find_candidate_set(request: IssueRequest) -> CandidateSet:
    evidence = request.calibration.evidence
    threshold = request.threshold
    points = comparison_breakpoints(evidence)
    accepted_points = {
        point for point in points if count_qualifying_specimens(evidence, point) >= threshold
    }
    pieces = [ClosedRegion(point, point) for point in accepted_points]
    for lower, upper, witness in _open_cells(points):
        if count_qualifying_specimens(evidence, witness) < threshold:
            continue
        # Close each qualifying cell only at endpoints that also meet the count.
        lower_accepted = lower is None or lower in accepted_points
        upper_accepted = upper is None or upper in accepted_points
        if lower_accepted and upper_accepted:
            pieces.append(ClosedRegion(lower, upper))
    return CandidateSet(tuple(pieces))
