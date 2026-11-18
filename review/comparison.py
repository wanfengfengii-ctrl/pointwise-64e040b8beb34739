from fractions import Fraction

from calibration.evidence import FrozenEvidence


def count_qualifying_specimens(evidence: FrozenEvidence, candidate: Fraction) -> int:
    target_magnitude = abs(evidence.target.at(candidate))
    return 1 + sum(
        abs(residual.at(candidate)) >= target_magnitude for _, residual in evidence.originals
    )


def comparison_breakpoints(evidence: FrozenEvidence) -> tuple[Fraction, ...]:
    """Find finite roots of each signed affine equality with the target."""
    target = evidence.target
    roots = set()
    for _, residual in evidence.originals:
        for sign in (-1, 1):
            intercept = residual.intercept - sign * target.intercept
            slope = residual.slope - sign * target.slope
            if slope:
                roots.add(-intercept / slope)
    return tuple(sorted(roots))
