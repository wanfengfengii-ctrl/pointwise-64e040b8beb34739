import json
import sqlite3

from handoff.lookup import read_report
from handoff.registry import ReportRecord


def encode_report(report: ReportRecord) -> str:
    return json.dumps(
        {
            "report_id": report.report_id,
            "calibration_id": report.calibration_id,
            "protocol_id": report.protocol_id,
            "source_revision_id": report.source_revision_id,
            "threshold": report.threshold,
            "candidate_regions": report.candidates.to_payload(),
            "deviation_unit": "um",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def export_report(connection: sqlite3.Connection, report_id: int) -> str:
    return encode_report(read_report(connection, report_id))
