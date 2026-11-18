import json
import sqlite3
from contextlib import closing, contextmanager

from calibration.publish import freeze_calibration
from calibration.store import CalibrationStore
from cohort.intake import record_cohort
from cohort.retirement import retire_cohort
from handoff.database import open_database
from protocol.catalog import register_protocol
from review.issue import issue_report


TARGET = (0,)
EQUAL_RESPONSE_SPEEDS = ((-1, 0, 1), (-1, -1, 2))
EQUAL_RESPONSE_GROUPS = (("drop-A", ("A",)), ("drop-C", ("C",)))
TOUCH_SPEEDS = (0, 0, 0, 0)
TOUCH_DEVIATIONS = (0, 1, 3, 4)
TOUCH_GROUPS = (("keep-AB", ("C", "D")), ("keep-CD", ("A", "B")))


def record_line(db, speeds, deviations):
    rows = [
        {"specimen_id": chr(65 + index), "conditions": (speed,), "deviation_um": deviation}
        for index, (speed, deviation) in enumerate(zip(speeds, deviations, strict=True))
    ]
    protocol_id = register_protocol(db, "line speed", ["line_speed"])
    return protocol_id, record_cohort(db, protocol_id, rows)


@contextmanager
def forbid_source_measurements(db):
    """Block source reads for the lifetime of a check on a dedicated connection."""
    def authorize(action, name, _column, _database, _trigger):
        if action == sqlite3.SQLITE_READ and name == "cohort_measurements":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    db.set_authorizer(authorize)
    try:
        yield
    finally:
        db.set_authorizer(None)


@contextmanager
def reject_commit(db):
    """Deny SQLite COMMIT on a dedicated connection and allow rollback."""
    def authorize(action, name, _detail, _database, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and name == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    db.set_authorizer(authorize)
    try:
        yield
    finally:
        db.set_authorizer(None)


def main():
    with closing(open_database(":memory:")) as db:
        frozen = []
        for speeds in EQUAL_RESPONSE_SPEEDS:
            _, source_id = record_line(db, speeds, (0, 0, 0))
            frozen.append(freeze_calibration(db, source_id, TARGET))
            retire_cohort(db, source_id)
        with forbid_source_measurements(db):
            evidence = [CalibrationStore(db).get_calibration(number).evidence for number in frozen]
            results = [issue_report(db, number, 2).candidates.to_payload() for number in frozen]
        if evidence[0] != evidence[1] or results != [[[[0, 1], [0, 1]]]] * 2:
            raise AssertionError("unexpected V1 response for the two full cohorts")
        print(json.dumps({"v1_candidate_regions": results}))


if __name__ == "__main__":
    main()
