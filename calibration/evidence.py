from dataclasses import dataclass
from fractions import Fraction

from calibration.design import CalibrationDesign
from calibration.least_squares import residual_vector
from protocol.rationals import RationalInput, parse_rational


@dataclass(frozen=True)
class AffineResidual:
    intercept: Fraction
    slope: Fraction

    def at(self, candidate: Fraction) -> Fraction:
        return self.intercept + self.slope * candidate


@dataclass(frozen=True)
class FrozenEvidence:
    originals: tuple[tuple[str, AffineResidual], ...]
    target: AffineResidual

    def __post_init__(self) -> None:
        identifiers = {specimen_id for specimen_id, _ in self.originals}
        if not identifiers or len(identifiers) != len(self.originals):
            raise ValueError("evidence needs at least one uniquely identified original specimen")

    @property
    def total_specimens(self) -> int:
        return len(self.originals) + 1

    def residuals_at(self, candidate: RationalInput) -> tuple[Fraction, ...]:
        value = parse_rational(candidate)
        return tuple(residual.at(value) for _, residual in self.originals) + (self.target.at(value),)


def build_evidence(design: CalibrationDesign) -> FrozenEvidence:
    # The projection is linear on responses for this fixed design.
    at_zero = residual_vector(design.matrix, design.response_at(Fraction(0)))
    at_one = residual_vector(design.matrix, design.response_at(Fraction(1)))
    response = tuple(AffineResidual(zero, one - zero) for zero, one in zip(at_zero, at_one))
    return FrozenEvidence(tuple(zip(design.specimen_ids, response[:-1])), response[-1])
