from dataclasses import dataclass
from fractions import Fraction

from cohort.records import CohortRevision
from protocol.catalog import ProtocolRevision
from protocol.covariates import ConditionInput
from protocol.validation import validate_conditions


@dataclass(frozen=True)
class CalibrationDesign:
    specimen_ids: tuple[str, ...]
    matrix: tuple[tuple[Fraction, ...], ...]
    observed_deviations: tuple[Fraction, ...]
    target_conditions: tuple[Fraction, ...]

    def response_at(self, candidate: Fraction) -> tuple[Fraction, ...]:
        return self.observed_deviations + (candidate,)


def build_design(
    cohort: CohortRevision, protocol: ProtocolRevision, target: ConditionInput
) -> CalibrationDesign:
    if protocol.revision_id != cohort.protocol_id:
        raise ValueError("design protocol must match the source revision")
    target_conditions = validate_conditions(protocol.covariates, target)
    intercept = Fraction(1)
    originals = tuple((intercept, *row.conditions) for row in cohort.measurements)
    return CalibrationDesign(
        tuple(row.specimen_id for row in cohort.measurements),
        originals + ((intercept, *target_conditions),),
        tuple(row.deviation_um for row in cohort.measurements),
        target_conditions,
    )
