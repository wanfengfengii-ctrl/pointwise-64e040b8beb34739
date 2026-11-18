import sqlite3
from collections.abc import Callable
from typing import Optional

from calibration.scenarios import ScenarioStore
from handoff.registry import ReportRecord, ReportRegistry
from handoff.robust_registry import REPORTED_GROUPS, RobustReportRecord, RobustReportRegistry
from protocol.identifiers import require_business_id
from review.regions import find_candidate_set
from review.request import prepare_issue_request
from review.robust_regions import find_robust_candidate_set


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


def validate_gates(k: object, q: object, group_sizes: tuple[int, ...]) -> None:
    """k and q are non-boolean positive integers, bounded by the frozen scenarios."""
    if type(k) is not int or k < 1:
        raise ValueError("k must be a positive integer")
    if type(q) is not int or q < 1:
        raise ValueError("q must be a positive integer")
    if not group_sizes:
        raise ValueError("the evidence has no scenario groups")
    limit = min(group_sizes)
    if k > limit:
        raise ValueError(f"k must not exceed {limit}, the smallest scenario specimen count")
    if q > len(group_sizes):
        raise ValueError(f"q must not exceed {len(group_sizes)} scenario groups")


def issue_robust(
    connection: sqlite3.Connection,
    evidence_id: int,
    k: object,
    q: object,
    *,
    before_commit: Optional[Callable[[], None]] = None,
) -> RobustReportRecord:
    """Issue from the frozen evidence alone; the source measurements are never read."""
    require_business_id(evidence_id, "evidence id")
    scenarios = ScenarioStore(connection).get_scenarios(evidence_id)
    evidences = tuple(scenarios.group_evidence(group) for group in scenarios.groups)
    group_sizes = tuple(evidence.total_specimens for evidence in evidences)
    validate_gates(k, q, group_sizes)
    candidates = find_robust_candidate_set(evidences, k, q)
    reported: REPORTED_GROUPS = tuple(
        (group.name, group.specimen_ids) for group in scenarios.groups
    )
    return RobustReportRegistry(connection).commit_report(
        scenarios.evidence_id, reported, k, q, candidates, before_commit=before_commit
    )
