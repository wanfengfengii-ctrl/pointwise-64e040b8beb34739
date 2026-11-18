from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Union

from protocol.rationals import RationalInput, parse_rational


ConditionInput = Union[Mapping[str, RationalInput], Sequence[RationalInput]]


@dataclass(frozen=True)
class CovariateOrder:
    names: tuple[str, ...]

    def encode(self, values: ConditionInput) -> tuple[Fraction, ...]:
        if isinstance(values, Mapping):
            if values.keys() != set(self.names):
                raise ValueError("condition fields must match the protocol")
            return tuple(parse_rational(values[name]) for name in self.names)

        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            raise ValueError("conditions must be a sequence or a keyed mapping")
        if len(values) != len(self.names):
            raise ValueError("condition length must match the protocol")
        return tuple(parse_rational(value) for value in values)


def make_covariate_order(names: Sequence[str]) -> CovariateOrder:
    if not isinstance(names, Sequence) or isinstance(names, (str, bytes, bytearray)):
        raise ValueError("covariates must be an ordered sequence of names")
    names = tuple(names)
    if not 1 <= len(names) <= 4:
        raise ValueError("a protocol needs one to four covariates")
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("covariate names must be nonblank strings")
    if len(set(names)) != len(names):
        raise ValueError("duplicate covariate name")
    return CovariateOrder(names)
