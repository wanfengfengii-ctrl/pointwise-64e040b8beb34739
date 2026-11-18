from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from protocol.rationals import RationalInput, decode_rational, encode_rational, parse_rational


Endpoint = Optional[Fraction]
RegionPayload = list[Optional[list[int]]]


@dataclass(frozen=True)
class ClosedRegion:
    lower: Endpoint
    upper: Endpoint

    def __post_init__(self) -> None:
        if self.lower is not None:
            object.__setattr__(self, "lower", parse_rational(self.lower))
        if self.upper is not None:
            object.__setattr__(self, "upper", parse_rational(self.upper))
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("region lower bound exceeds its upper bound")

    def covers(self, value: Fraction) -> bool:
        return (self.lower is None or self.lower <= value) and (
            self.upper is None or value <= self.upper
        )


def normalize_regions(regions: Iterable[ClosedRegion]) -> tuple[ClosedRegion, ...]:
    ordered = sorted(regions, key=lambda part: (part.lower is not None, part.lower))
    merged = []
    for part in ordered:
        if not merged:
            merged.append(part)
            continue
        previous = merged[-1]
        if previous.upper is not None and part.lower is not None and previous.upper < part.lower:
            merged.append(part)
            continue
        upper = None
        if previous.upper is not None and part.upper is not None:
            upper = max(previous.upper, part.upper)
        merged[-1] = ClosedRegion(previous.lower, upper)
    return tuple(merged)


@dataclass(frozen=True)
class CandidateSet:
    regions: tuple[ClosedRegion, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "regions", normalize_regions(self.regions))

    def __contains__(self, candidate: RationalInput) -> bool:
        value = parse_rational(candidate)
        return any(region.covers(value) for region in self.regions)

    def to_payload(self) -> list[RegionPayload]:
        return [
            [encode_rational(endpoint) if endpoint is not None else None for endpoint in (region.lower, region.upper)]
            for region in self.regions
        ]

    @classmethod
    def from_payload(cls, payload: list[RegionPayload]) -> "CandidateSet":
        regions = []
        for lower, upper in payload:
            regions.append(ClosedRegion(
                decode_rational(lower) if lower is not None else None,
                decode_rational(upper) if upper is not None else None,
            ))
        return cls(tuple(regions))
