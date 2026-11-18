import sqlite3

from handoff.registry import ReportRecord, ReportRegistry


def read_report(connection: sqlite3.Connection, report_id: int) -> ReportRecord:
    """Retrieve the committed record by its own report number."""
    return ReportRegistry(connection).get_report(report_id)
