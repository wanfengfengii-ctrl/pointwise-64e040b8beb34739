import json
import sqlite3
from dataclasses import dataclass

from handoff.transactions import write_transaction
from review.region_set import CandidateSet


REPORTED_GROUPS = tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class RobustReportRecord:
    report_id: int
    evidence_id: int
    groups: REPORTED_GROUPS
    k: int
    q: int
    candidates: CandidateSet


def _encode_groups(groups: REPORTED_GROUPS) -> list[list[object]]:
    return [[name, list(specimen_ids)] for name, specimen_ids in groups]


def _decode_groups(payload: list[list[object]]) -> REPORTED_GROUPS:
    return tuple((name, tuple(specimen_ids)) for name, specimen_ids in payload)


def create_robust_report_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS robust_reports (
            id INTEGER PRIMARY KEY,
            evidence_id INTEGER NOT NULL REFERENCES scenario_evidences(id),
            k INTEGER NOT NULL CHECK (k >= 1),
            q INTEGER NOT NULL CHECK (q >= 1),
            body TEXT NOT NULL
        )
        """
    )


class RobustReportRegistry:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def commit_report(
        self,
        evidence_id: int,
        groups: REPORTED_GROUPS,
        k: int,
        q: int,
        candidates: CandidateSet,
        *,
        before_commit=None,
    ) -> RobustReportRecord:
        body = json.dumps({
            "groups": _encode_groups(groups),
            "candidate_regions": candidates.to_payload(),
        })
        with write_transaction(self.connection, before_commit=before_commit):
            cursor = self.connection.execute(
                "INSERT INTO robust_reports (evidence_id, k, q, body) VALUES (?, ?, ?, ?)",
                (evidence_id, k, q, body),
            )
            report_id = cursor.lastrowid
        return RobustReportRecord(report_id, evidence_id, groups, k, q, candidates)

    def get_report(self, report_id: int) -> RobustReportRecord:
        row = self.connection.execute(
            "SELECT id, evidence_id, k, q, body FROM robust_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown robust report {report_id}")
        identifier, evidence_id, k, q, encoded_body = row
        body = json.loads(encoded_body)
        return RobustReportRecord(
            identifier,
            evidence_id,
            _decode_groups(body["groups"]),
            k,
            q,
            CandidateSet.from_payload(body["candidate_regions"]),
        )

    def list_ids(self) -> tuple[int, ...]:
        return tuple(row[0] for row in self.connection.execute(
            "SELECT id FROM robust_reports ORDER BY id"
        ))
