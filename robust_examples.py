import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from calibration.publish import freeze_calibration, freeze_scenarios
from calibration.store import CalibrationStore
from cohort.intake import record_cohort
from cohort.retirement import retire_cohort
from handoff.database import open_database
from handoff.lookup import read_robust
from protocol.catalog import register_protocol
from review.issue import issue_report, issue_robust


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
        check_robust_examples(db)


def check_robust_examples(db):
    """Verify the documented robust results, including a reopen on a fresh connection."""
    with TemporaryDirectory() as directory:
        path = Path(directory) / "coating.sqlite3"
        with closing(open_database(path)) as fresh:
            _, source_id = record_line(fresh, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
            evidence_id = freeze_scenarios(fresh, source_id, TARGET, TOUCH_GROUPS)
            retire_cohort(fresh, source_id)
            with forbid_source_measurements(fresh):
                wide = issue_robust(fresh, evidence_id, 2, 1)
                point = issue_robust(fresh, evidence_id, 2, 2)
        expected_wide = [[[-1, 1], [5, 1]]]
        expected_point = [[[2, 1], [2, 1]]]
        if wide.candidates.to_payload() != expected_wide:
            raise AssertionError("unexpected robust union for the touch example")
        if point.candidates.to_payload() != expected_point:
            raise AssertionError("unexpected robust intersection for the touch example")
        with closing(open_database(path)) as reopened:
            fixed = read_robust(reopened, point.report_id)
        if fixed != point or fixed.groups != TOUCH_GROUPS or fixed.k != 2 or fixed.q != 2:
            raise AssertionError("reopened robust report differs from the issued one")
        print(json.dumps({
            "robust_union": wide.candidates.to_payload(),
            "robust_intersection": point.candidates.to_payload(),
            "robust_reopened": fixed.candidates.to_payload(),
        }))


if __name__ == "__main__":
    main()
