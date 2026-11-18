import sqlite3
from dataclasses import dataclass

from calibration.store import CalibrationStore, FrozenCalibration


@dataclass(frozen=True)
class IssueRequest:
    calibration: FrozenCalibration
    threshold: int


def validate_threshold(threshold: int, total_specimens: int) -> None:
    if type(threshold) is not int or not 1 <= threshold <= total_specimens:
        raise ValueError(f"k must be an integer from 1 to {total_specimens}")


def prepare_issue_request(
    connection: sqlite3.Connection, calibration_id: int, k: int
) -> IssueRequest:
    calibration = CalibrationStore(connection).get_calibration(calibration_id)
    validate_threshold(k, calibration.evidence.total_specimens)
    return IssueRequest(calibration, k)
