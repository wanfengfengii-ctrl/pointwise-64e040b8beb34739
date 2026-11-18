import sqlite3
from collections.abc import Callable
from typing import Optional

from handoff.registry import ReportRecord, ReportRegistry
from review.regions import find_candidate_set
from review.request import prepare_issue_request


def issue_report(
    connection: sqlite3.Connection,
    calibration_id: int,
    k: int,
    *,
    before_commit: Optional[Callable[[], None]] = None,
) -> ReportRecord:
    request = prepare_issue_request(connection, calibration_id, k)
    candidates = find_candidate_set(request)
    return ReportRegistry(connection).commit_report(
        request.calibration, request.threshold, candidates, before_commit=before_commit
    )
