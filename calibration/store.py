import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from calibration.evidence import AffineResidual, FrozenEvidence
from protocol.rationals import decode_rational, encode_rational


@dataclass(frozen=True)
class FrozenCalibration:
    calibration_id: int
    source_revision_id: int
    protocol_id: int
    target_conditions: tuple[Fraction, ...]
    evidence: FrozenEvidence


def create_calibration_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY,
            source_revision_id INTEGER NOT NULL,
            protocol_id INTEGER NOT NULL REFERENCES protocol_revisions(id),
            target_conditions TEXT NOT NULL,
            evidence TEXT NOT NULL,
            FOREIGN KEY (source_revision_id, protocol_id) REFERENCES cohort_revisions(id, protocol_id)
        )
        """
    )


def _encode_residual(residual: AffineResidual) -> list[list[int]]:
    return [encode_rational(residual.intercept), encode_rational(residual.slope)]


def _decode_residual(payload: list[list[int]]) -> AffineResidual:
    intercept, slope = payload
    return AffineResidual(decode_rational(intercept), decode_rational(slope))


class CalibrationStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def insert_calibration(
        self,
        source_revision_id: int,
        protocol_id: int,
        target_conditions: tuple[Fraction, ...],
        evidence: FrozenEvidence,
    ) -> int:
        encoded_evidence = {
            "originals": [[specimen_id, _encode_residual(residual)] for specimen_id, residual in evidence.originals],
            "target": _encode_residual(evidence.target),
        }
        cursor = self.connection.execute(
            """
            INSERT INTO calibrations (source_revision_id, protocol_id, target_conditions, evidence)
            VALUES (?, ?, ?, ?)
            """,
            (
                source_revision_id,
                protocol_id,
                json.dumps([encode_rational(value) for value in target_conditions]),
                json.dumps(encoded_evidence, ensure_ascii=False),
            ),
        )
        return cursor.lastrowid

    def get_calibration(self, calibration_id: int) -> FrozenCalibration:
        row = self.connection.execute(
            """
            SELECT id, source_revision_id, protocol_id, target_conditions, evidence
            FROM calibrations WHERE id = ?
            """,
            (calibration_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown calibration {calibration_id}")
        identifier, source_id, protocol_id, target, raw_evidence = row
        payload = json.loads(raw_evidence)
        evidence = FrozenEvidence(
            tuple((specimen_id, _decode_residual(residual)) for specimen_id, residual in payload["originals"]),
            _decode_residual(payload["target"]),
        )
        return FrozenCalibration(
            identifier,
            source_id,
            protocol_id,
            tuple(decode_rational(value) for value in json.loads(target)),
            evidence,
        )

    def list_ids(self) -> tuple[int, ...]:
        return tuple(row[0] for row in self.connection.execute(
            "SELECT id FROM calibrations ORDER BY id"
        ))
