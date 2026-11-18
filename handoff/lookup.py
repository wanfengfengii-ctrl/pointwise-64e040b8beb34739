import sqlite3

from handoff.registry import ReportRecord, ReportRegistry
from handoff.robust_registry import RobustReportRecord, RobustReportRegistry
from protocol.identifiers import require_business_id


def read_report(connection: sqlite3.Connection, report_id: int) -> ReportRecord:
    """Retrieve the committed record by its own report number."""
    return ReportRegistry(connection).get_report(report_id)


def read_robust(connection: sqlite3.Connection, report_id: int) -> RobustReportRecord:
    """Retrieve a robust report exactly as issued, without recomputation."""
    require_business_id(report_id, "report id")
    return RobustReportRegistry(connection).get_report(report_id)
