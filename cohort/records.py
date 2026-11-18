from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from protocol.catalog import ProtocolRevision
from protocol.covariates import ConditionInput
from protocol.rationals import RationalInput
from protocol.units import parse_deviation_um
from protocol.validation import validate_conditions


@dataclass(frozen=True)
class SpecimenMeasurement:
    specimen_id: str
    conditions: tuple[Fraction, ...]
    deviation_um: Fraction


@dataclass(frozen=True)
class CohortRevision:
    revision_id: int
    protocol_id: int
    parent_revision_id: Optional[int]
    retired: bool
    measurements: tuple[SpecimenMeasurement, ...]


def build_measurement(
    protocol: ProtocolRevision,
    specimen_id: str,
    conditions: ConditionInput,
    deviation_um: RationalInput,
) -> SpecimenMeasurement:
    if not isinstance(specimen_id, str) or not specimen_id.strip():
        raise ValueError("specimen id must be a nonblank string")
    return SpecimenMeasurement(
        specimen_id,
        validate_conditions(protocol.covariates, conditions),
        parse_deviation_um(deviation_um),
    )
