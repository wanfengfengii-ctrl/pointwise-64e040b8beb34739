from fractions import Fraction
from typing import Union


RationalInput = Union[int, str, Fraction]


def parse_rational(value: RationalInput) -> Fraction:
    """Read a rational value without going through binary floating point."""
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f"invalid rational value {value!r}") from error
    raise ValueError("expected an integer, Fraction, or rational string")


def encode_rational(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def decode_rational(payload: list[int]) -> Fraction:
    if (
        not isinstance(payload, list)
        or len(payload) != 2
        or any(type(part) is not int for part in payload)
        or payload[1] <= 0
    ):
        raise ValueError("expected a numerator and a positive denominator")
    return Fraction(payload[0], payload[1])
