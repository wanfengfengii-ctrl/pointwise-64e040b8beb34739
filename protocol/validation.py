from collections.abc import Sequence
from fractions import Fraction

from protocol.covariates import ConditionInput, CovariateOrder, make_covariate_order
from protocol.units import validate_deviation_unit


def validate_protocol_definition(
    name: str, covariates: Sequence[str], deviation_unit: str
) -> tuple[CovariateOrder, str]:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("protocol name must be a nonblank string")
    return make_covariate_order(covariates), validate_deviation_unit(deviation_unit)


def validate_conditions(
    order: CovariateOrder, values: ConditionInput
) -> tuple[Fraction, ...]:
    return order.encode(values)
