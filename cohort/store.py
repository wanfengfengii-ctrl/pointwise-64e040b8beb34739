import json
import sqlite3
from typing import Optional

from cohort.records import CohortRevision, SpecimenMeasurement
from protocol.rationals import decode_rational, encode_rational


class SourceRetiredError(ValueError):
    """The revision exists but cannot be used to create new work."""


def create_cohort_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cohort_revisions (
            id INTEGER PRIMARY KEY,
            protocol_id INTEGER NOT NULL REFERENCES protocol_revisions(id),
            parent_id INTEGER,
            retired INTEGER NOT NULL DEFAULT 0 CHECK (retired IN (0, 1)),
            UNIQUE (id, protocol_id),
            FOREIGN KEY (parent_id, protocol_id) REFERENCES cohort_revisions(id, protocol_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cohort_measurements (
            revision_id INTEGER NOT NULL REFERENCES cohort_revisions(id),
            specimen_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            conditions TEXT NOT NULL,
            deviation_um TEXT NOT NULL,
            PRIMARY KEY (revision_id, specimen_id),
            UNIQUE (revision_id, position)
        )
        """
    )


class CohortStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def insert_revision(
        self,
        protocol_id: int,
        parent_revision_id: Optional[int],
        measurements: tuple[SpecimenMeasurement, ...],
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO cohort_revisions (protocol_id, parent_id) VALUES (?, ?)",
            (protocol_id, parent_revision_id),
        )
        revision_id = cursor.lastrowid
        encoded_rows = (
            (
                revision_id,
                measurement.specimen_id,
                position,
                json.dumps([encode_rational(value) for value in measurement.conditions]),
                json.dumps(encode_rational(measurement.deviation_um)),
            )
            for position, measurement in enumerate(measurements)
        )
        self.connection.executemany(
            """
            INSERT INTO cohort_measurements (revision_id, specimen_id, position, conditions, deviation_um)
            VALUES (?, ?, ?, ?, ?)
            """,
            encoded_rows,
        )
        return revision_id

    def _read_revision(self, revision_id: int, *, available_only: bool) -> CohortRevision:
        row = self.connection.execute(
            "SELECT id, protocol_id, parent_id, retired FROM cohort_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown cohort revision {revision_id}")
        identifier, protocol_id, parent_id, retired = row
        if available_only and retired:
            raise SourceRetiredError(f"cohort revision {revision_id} is retired")

        rows = self.connection.execute(
            """
            SELECT specimen_id, conditions, deviation_um
            FROM cohort_measurements WHERE revision_id = ? ORDER BY position
            """,
            (identifier,),
        )
        measurements = tuple(
            SpecimenMeasurement(
                specimen_id,
                tuple(decode_rational(value) for value in json.loads(conditions)),
                decode_rational(json.loads(deviation_um)),
            )
            for specimen_id, conditions, deviation_um in rows
        )
        return CohortRevision(identifier, protocol_id, parent_id, bool(retired), measurements)

    def get_revision(self, revision_id: int) -> CohortRevision:
        return self._read_revision(revision_id, available_only=False)

    def require_available(self, revision_id: int) -> CohortRevision:
        return self._read_revision(revision_id, available_only=True)

    def mark_retired(self, revision_id: int) -> None:
        cursor = self.connection.execute(
            "UPDATE cohort_revisions SET retired = 1 WHERE id = ?", (revision_id,)
        )
        if cursor.rowcount == 0:
            raise KeyError(f"unknown cohort revision {revision_id}")

    def list_ids(self) -> tuple[int, ...]:
        return tuple(row[0] for row in self.connection.execute(
            "SELECT id FROM cohort_revisions ORDER BY id"
        ))
