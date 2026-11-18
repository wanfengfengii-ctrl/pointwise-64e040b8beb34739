import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from calibration.store import FrozenCalibration
from handoff.transactions import write_transaction
from review.region_set import CandidateSet


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    calibration_id: int
    protocol_id: int
    source_revision_id: int
    threshold: int
    candidates: CandidateSet


def create_report_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            calibration_id INTEGER NOT NULL REFERENCES calibrations(id),
            threshold INTEGER NOT NULL CHECK (threshold >= 1),
            body TEXT NOT NULL
        )
        """
    )


class ReportRegistry:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def commit_report(
        self,
        calibration: FrozenCalibration,
        threshold: int,
        candidates: CandidateSet,
        *,
        before_commit: Optional[Callable[[], None]] = None,
    ) -> ReportRecord:
        body = json.dumps({
            "protocol_id": calibration.protocol_id,
            "source_revision_id": calibration.source_revision_id,
            "candidate_regions": candidates.to_payload(),
        })
        with write_transaction(self.connection, before_commit=before_commit):
            cursor = self.connection.execute(
                "INSERT INTO reports (calibration_id, threshold, body) VALUES (?, ?, ?)",
                (calibration.calibration_id, threshold, body),
            )
            report_id = cursor.lastrowid
        return ReportRecord(
            report_id,
            calibration.calibration_id,
            calibration.protocol_id,
            calibration.source_revision_id,
            threshold,
            candidates,
        )

    def get_report(self, report_id: int) -> ReportRecord:
        row = self.connection.execute(
            "SELECT id, calibration_id, threshold, body FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown report {report_id}")
        identifier, calibration_id, threshold, encoded_body = row
        body = json.loads(encoded_body)
        return ReportRecord(
            identifier,
            calibration_id,
            body["protocol_id"],
            body["source_revision_id"],
            threshold,
            CandidateSet.from_payload(body["candidate_regions"]),
        )

    def list_ids(self) -> tuple[int, ...]:
        return tuple(row[0] for row in self.connection.execute("SELECT id FROM reports ORDER BY id"))
