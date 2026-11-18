from collections.abc import Sequence
from fractions import Fraction


def _dot(left: Sequence[Fraction], right: Sequence[Fraction]) -> Fraction:
    return sum((a * b for a, b in zip(left, right)), Fraction(0))


def fitted_values(
    rows: Sequence[Sequence[Fraction]], response: Sequence[Fraction]
) -> tuple[Fraction, ...]:
    """Project the response onto the column space with rational arithmetic."""
    if not rows or len(rows) != len(response):
        raise ValueError("design rows and response must have the same nonzero length")
    width = len(rows[0])
    if not width or any(len(row) != width for row in rows):
        raise ValueError("design must be a nonempty rectangular matrix")

    basis = []
    fitted = [Fraction(0) for _ in rows]
    for column in zip(*rows):
        direction = column
        for vector, squared_norm in basis:
            scale = _dot(direction, vector) / squared_norm
            direction = tuple(value - scale * entry for value, entry in zip(direction, vector))
        squared_norm = _dot(direction, direction)
        if squared_norm == 0:
            continue
        basis.append((direction, squared_norm))
        coefficient = _dot(response, direction) / squared_norm
        for index, value in enumerate(direction):
            fitted[index] += coefficient * value
    return tuple(fitted)


def residual_vector(
    rows: Sequence[Sequence[Fraction]], response: Sequence[Fraction]
) -> tuple[Fraction, ...]:
    fitted = fitted_values(rows, response)
    return tuple(observed - predicted for observed, predicted in zip(response, fitted))
