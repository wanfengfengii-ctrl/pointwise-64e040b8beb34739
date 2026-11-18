from fractions import Fraction

from protocol.rationals import RationalInput, parse_rational


MICROMETRE = "um"


def validate_deviation_unit(unit: str) -> str:
    if unit not in (MICROMETRE, "µm", "μm", "微米"):
        raise ValueError("thickness deviations must be measured in micrometres")
    return MICROMETRE


def parse_deviation_um(value: RationalInput) -> Fraction:
    return parse_rational(value)
