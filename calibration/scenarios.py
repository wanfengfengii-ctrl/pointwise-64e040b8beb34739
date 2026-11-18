import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from calibration.design import CalibrationDesign
from calibration.evidence import FrozenEvidence, build_evidence
from cohort.records import CohortRevision, SpecimenMeasurement
from protocol.identifiers import require_business_id
from protocol.rationals import decode_rational, encode_rational


@dataclass(frozen=True)
class ScenarioGroup:
    """A named exclusion scenario: the listed source specimens are dropped."""

    name: str
    specimen_ids: tuple[str, ...]


@dataclass(frozen=True)
class FrozenScenarios:
    """A self-contained snapshot: target, named groups, and the source measurements."""

    evidence_id: int
    source_revision_id: int
    protocol_id: int
    target_conditions: tuple[Fraction, ...]
    groups: tuple[ScenarioGroup, ...]
    measurements: tuple[SpecimenMeasurement, ...]

    def retained(self, group: ScenarioGroup) -> tuple[SpecimenMeasurement, ...]:
        dropped = set(group.specimen_ids)
        return tuple(
            measurement for measurement in self.measurements
            if measurement.specimen_id not in dropped
        )

    def group_evidence(self, group: ScenarioGroup) -> FrozenEvidence:
        """Refit this group's retained originals plus the shared target, exactly."""
        retained = self.retained(group)
        intercept = Fraction(1)
        design = CalibrationDesign(
            tuple(measurement.specimen_id for measurement in retained),
            tuple((intercept, *measurement.conditions) for measurement in retained)
            + ((intercept, *self.target_conditions),),
            tuple(measurement.deviation_um for measurement in retained),
            self.target_conditions,
        )
        return build_evidence(design)


def validate_scenario_groups(
    cohort: CohortRevision, groups: object
) -> tuple[ScenarioGroup, ...]:
    if not isinstance(groups, (list, tuple)):
        raise ValueError("groups must be a nonempty list or tuple of scenarios")
    if not groups:
        raise ValueError("at least one scenario group is required")

    known = {measurement.specimen_id for measurement in cohort.measurements}
    parsed = []
    seen_names: set[str] = set()
    for item in groups:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("each scenario must be a (name, specimen_ids) pair")
        name, specimen_ids = item
        if not isinstance(name, str) or not name.strip():
            raise ValueError("scenario names must be nonblank strings")
        if name in seen_names:
            raise ValueError(f"duplicate scenario name {name!r}")
        seen_names.add(name)

        if not isinstance(specimen_ids, (list, tuple)) or not specimen_ids:
            raise ValueError("a scenario needs a nonempty list or tuple of specimen ids")
        identifiers = tuple(specimen_ids)
        if any(not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers):
            raise ValueError("specimen ids must be nonblank strings")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"duplicate specimen id in scenario {name!r}")
        unknown = [identifier for identifier in identifiers if identifier not in known]
        if unknown:
            raise ValueError(f"scenario {name!r} refers to unknown specimens {sorted(unknown)!r}")
        if len(identifiers) >= len(known):
            raise ValueError(
                f"scenario {name!r} must drop and retain at least one original specimen"
            )
        parsed.append(ScenarioGroup(name, identifiers))
    return tuple(parsed)


def encode_groups(groups: Sequence[ScenarioGroup]) -> list[list[object]]:
    return [[group.name, list(group.specimen_ids)] for group in groups]


def decode_groups(payload: Sequence[Sequence[object]]) -> tuple[ScenarioGroup, ...]:
    return tuple(ScenarioGroup(name, tuple(identifiers)) for name, identifiers in payload)


def encode_measurements(measurements: Sequence[SpecimenMeasurement]) -> list[list[object]]:
    return [
        [
            measurement.specimen_id,
            [encode_rational(value) for value in measurement.conditions],
            encode_rational(measurement.deviation_um),
        ]
        for measurement in measurements
    ]


def decode_measurements(payload: Sequence[Sequence[object]]) -> tuple[SpecimenMeasurement, ...]:
    return tuple(
        SpecimenMeasurement(
            specimen_id,
            tuple(decode_rational(value) for value in conditions),
            decode_rational(deviation),
        )
        for specimen_id, conditions, deviation in payload
    )


def create_scenario_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scenario_evidences (
            id INTEGER PRIMARY KEY,
            source_revision_id INTEGER NOT NULL,
            protocol_id INTEGER NOT NULL REFERENCES protocol_revisions(id),
            target_conditions TEXT NOT NULL,
            groups TEXT NOT NULL,
            measurements TEXT NOT NULL,
            FOREIGN KEY (source_revision_id, protocol_id) REFERENCES cohort_revisions(id, protocol_id)
        )
        """
    )


class ScenarioStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def insert_scenarios(
        self,
        source_revision_id: int,
        protocol_id: int,
        target_conditions: tuple[Fraction, ...],
        groups: tuple[ScenarioGroup, ...],
        measurements: tuple[SpecimenMeasurement, ...],
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO scenario_evidences
                (source_revision_id, protocol_id, target_conditions, groups, measurements)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_revision_id,
                protocol_id,
                json.dumps([encode_rational(value) for value in target_conditions]),
                json.dumps(encode_groups(groups), ensure_ascii=False),
                json.dumps(encode_measurements(measurements), ensure_ascii=False),
            ),
        )
        return cursor.lastrowid

    def get_scenarios(self, evidence_id: int) -> FrozenScenarios:
        require_business_id(evidence_id, "evidence id")
        row = self.connection.execute(
            """
            SELECT id, source_revision_id, protocol_id, target_conditions, groups, measurements
            FROM scenario_evidences WHERE id = ?
            """,
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown scenario evidence {evidence_id}")
        identifier, source_id, protocol_id, target, groups, measurements = row
        return FrozenScenarios(
            identifier,
            source_id,
            protocol_id,
            tuple(decode_rational(value) for value in json.loads(target)),
            decode_groups(json.loads(groups)),
            decode_measurements(json.loads(measurements)),
        )

    def list_ids(self) -> tuple[int, ...]:
        return tuple(row[0] for row in self.connection.execute(
            "SELECT id FROM scenario_evidences ORDER BY id"
        ))
