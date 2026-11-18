import json
from contextlib import closing

from calibration.publish import freeze_calibration
from calibration.store import CalibrationStore
from cohort.retirement import retire_cohort
from cohort.revisions import correct_cohort
from cohort.store import CohortStore, SourceRetiredError
from handoff.database import initialize_database, open_database
from handoff.export import export_report
from handoff.lookup import read_report
from handoff.registry import ReportRegistry
from protocol.catalog import ProtocolCatalog
from review.issue import issue_report
from review.region_set import ClosedRegion
from tests.support import DatabaseTestCase, emit_scenario, measurement


class CommitBlocked(RuntimeError):
    pass


def block_commit():
    raise CommitBlocked("report commit blocked")


class HandoffTests(DatabaseTestCase):
    def test_rollback(self):
        _, _, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        old = issue_report(self.db, calibration_id, 2)
        registry = ReportRegistry(self.db)
        staged_ids = []
        with closing(open_database(self.path)) as observer:
            def fail_after_write():
                staged_ids.extend(registry.list_ids())
                self.assertEqual(ReportRegistry(observer).list_ids(), (old.report_id,))
                block_commit()

            with self.assertRaisesRegex(CommitBlocked, "report commit blocked"):
                issue_report(self.db, calibration_id, 1, before_commit=fail_after_write)
            self.assertEqual(len(staged_ids), 2)
            self.assertEqual(staged_ids[0], old.report_id)
            self.assertEqual(registry.list_ids(), (old.report_id,))
            self.assertEqual(ReportRegistry(observer).list_ids(), (old.report_id,))
            with self.assertRaises(KeyError):
                read_report(self.db, staged_ids[1])
        self.assertEqual(read_report(self.db, old.report_id), old)

    def test_rollback_reopen_visibility(self):
        _, _, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        old = issue_report(self.db, calibration_id, 2)
        exported = export_report(self.db, old.report_id)
        with self.assertRaises(CommitBlocked):
            issue_report(self.db, calibration_id, 1, before_commit=block_commit)
        self.reopen()
        self.assertEqual(ReportRegistry(self.db).list_ids(), (old.report_id,))
        self.assertEqual(read_report(self.db, old.report_id), old)
        self.assertEqual(export_report(self.db, old.report_id), exported)

    def test_retired(self):
        _, source_id, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        old = issue_report(self.db, calibration_id, 2)
        retire_cohort(self.db, source_id)
        retire_cohort(self.db, source_id)
        self.reopen()
        self.assertTrue(CohortStore(self.db).get_revision(source_id).retired)
        with self.assertRaises(SourceRetiredError):
            freeze_calibration(self.db, source_id, (0,))
        self.assertEqual(CalibrationStore(self.db).list_ids(), (calibration_id,))
        retained = read_report(self.db, old.report_id)
        self.assertEqual(retained, old)
        self.assertEqual(retained.candidates.regions, (ClosedRegion(-3, 3),))
        self.assertEqual(json.loads(export_report(self.db, old.report_id))["candidate_regions"], [[[-3, 1], [3, 1]]])
        repeat = issue_report(self.db, calibration_id, 1)
        self.assertEqual(repeat.calibration_id, calibration_id)
        self.assertEqual(repeat.candidates.regions, (ClosedRegion(None, None),))

    def test_fixed_report_after_reissue(self):
        protocol_id, source_id, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        old = issue_report(self.db, calibration_id, 2)
        exported_on_issue = export_report(self.db, old.report_id)
        retire_cohort(self.db, source_id)
        self.reopen()
        exported_on_reopen = export_report(self.db, old.report_id)
        expected_old = {
            "report_id": old.report_id,
            "calibration_id": calibration_id,
            "source_revision_id": source_id,
            "protocol_id": protocol_id,
            "threshold": 2,
            "candidate_regions": [[[-3, 1], [3, 1]]],
            "deviation_unit": "um",
        }
        self.assertEqual(json.loads(exported_on_reopen), expected_old)
        self.assertEqual(exported_on_reopen, exported_on_issue)
        new = issue_report(self.db, calibration_id, 1)
        self.assertNotEqual(old.report_id, new.report_id)
        self.assertEqual(read_report(self.db, old.report_id), old)
        self.assertEqual(read_report(self.db, new.report_id), new)
        old_after = export_report(self.db, old.report_id)
        self.assertEqual(old_after, exported_on_reopen)
        expected_new = dict(expected_old, report_id=new.report_id, threshold=1, candidate_regions=[[None, None]])
        actual_new = json.loads(export_report(self.db, new.report_id))
        self.assertEqual(actual_new, expected_new)
        emit_scenario(
            "retired.fixed_report_after_reissue",
            {"source_revision": source_id, "calibration": calibration_id, "old_k": 2, "new_k": 1},
            expected_old,
            json.loads(old_after),
            {"new_report": expected_new, "original_bytes_preserved": True},
            {"new_report": actual_new, "original_bytes_preserved": old_after == exported_on_issue},
            ["cohort/retirement.py", "review/issue.py", "handoff/registry.py", "handoff/export.py"],
            "For the original k=2 report the same-speed mean gives [-3,3]. The target always counts itself at k=1. The first export was captured before retirement and used for the byte comparison.",
        )

    def test_reinitialize(self):
        protocol_id, source_id, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        child_id = correct_cohort(self.db, source_id, protocol_id, [measurement("A", (0,), -2)])
        old = issue_report(self.db, calibration_id, 2)
        retire_cohort(self.db, source_id)
        expected_calibration = CalibrationStore(self.db).get_calibration(calibration_id)
        expected_child = CohortStore(self.db).get_revision(child_id)
        initialize_database(self.db)
        initialize_database(self.db)
        self.reopen()
        self.assertEqual(ProtocolCatalog(self.db).list_ids(), (protocol_id,))
        self.assertEqual(CohortStore(self.db).list_ids(), (source_id, child_id))
        self.assertEqual(CohortStore(self.db).get_revision(child_id), expected_child)
        self.assertEqual(expected_child.parent_revision_id, source_id)
        self.assertFalse(expected_child.retired)
        self.assertEqual(expected_child.measurements[0].deviation_um, -2)
        self.assertEqual(CalibrationStore(self.db).get_calibration(calibration_id), expected_calibration)
        self.assertEqual(read_report(self.db, old.report_id), old)
        with self.assertRaises(SourceRetiredError):
            freeze_calibration(self.db, source_id, (0,))
        with self.assertRaises(SourceRetiredError):
            correct_cohort(self.db, source_id, protocol_id, [measurement("A", (0,), 1)])
        self.assertEqual(issue_report(self.db, calibration_id, 1).candidates.regions, (ClosedRegion(None, None),))
        corrected_calibration = freeze_calibration(self.db, child_id, (0,))
        self.assertEqual(issue_report(self.db, corrected_calibration, 2).candidates.regions, (ClosedRegion(-5, 4),))

    def test_unknown_ids(self):
        with self.assertRaisesRegex(KeyError, "unknown cohort revision"):
            retire_cohort(self.db, 99)
        with self.assertRaisesRegex(KeyError, "unknown report"):
            read_report(self.db, 99)
        with self.assertRaisesRegex(KeyError, "unknown report"):
            export_report(self.db, 99)
        self.assertEqual(CohortStore(self.db).list_ids(), ())
        self.assertEqual(ReportRegistry(self.db).list_ids(), ())
