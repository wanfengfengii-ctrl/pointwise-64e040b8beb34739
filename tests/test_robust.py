from fractions import Fraction as F

from calibration.publish import freeze_scenarios
from calibration.scenarios import ScenarioStore
from cohort.retirement import retire_cohort
from cohort.revisions import correct_cohort
from handoff.database import initialize_database
from handoff.lookup import read_robust, read_report
from handoff.registry import ReportRegistry
from handoff.robust_registry import RobustReportRegistry
from review.issue import issue_report, issue_robust
from review.robust_regions import find_robust_candidate_set
from robust_examples import (
    EQUAL_RESPONSE_GROUPS,
    TARGET,
    TOUCH_DEVIATIONS,
    TOUCH_GROUPS,
    TOUCH_SPEEDS,
    forbid_source_measurements,
    record_line,
)
from tests.support import DatabaseTestCase, measurement


class CommitBlocked(RuntimeError):
    pass


def block_commit():
    raise CommitBlocked("robust commit blocked")


class RobustFreezeTests(DatabaseTestCase):
    def test_freeze_binds_revision_and_preserves_order(self):
        _, source_id = record_line(self.db, (-1, 0, 1), (0, 0, 0))
        groups = (("drop-C", ["C"]), ("drop-A", ("A",)))
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, groups)
        frozen = ScenarioStore(self.db).get_scenarios(evidence_id)
        self.assertEqual(frozen.source_revision_id, source_id)
        self.assertEqual(frozen.target_conditions, (F(0),))
        self.assertEqual([(g.name, g.specimen_ids) for g in frozen.groups], [("drop-C", ("C",)), ("drop-A", ("A",))])
        self.assertEqual([m.specimen_id for m in frozen.measurements], ["A", "B", "C"])

    def test_freeze_rejects_invalid_groups(self):
        _, source_id = record_line(self.db, (0, 0, 0), (0, 0, 0))
        invalid = [
            None,
            (),
            "drop-A",
            [("dup", ("A",)), ("dup", ("B",))],
            [("", ("A",))],
            [(" ", ("A",))],
            [("g", ())],
            [("g", [])],
            [("g", ("A", "A"))],
            [("g", ("A", "Z"))],
            [("g", ("A", "B", "C"))],
            [("g", "A")],
            [("g", (1,))],
            [("g", ("A",), "extra")],
            [("g", (None,))],
        ]
        store = ScenarioStore(self.db)
        for groups in invalid:
            with self.subTest(groups=groups):
                with self.assertRaises(ValueError):
                    freeze_scenarios(self.db, source_id, TARGET, groups)
                self.assertEqual(store.list_ids(), ())

    def test_freeze_requires_available_revision(self):
        _, source_id = record_line(self.db, (0, 0), (0, 0))
        retire_cohort(self.db, source_id)
        with self.assertRaises(ValueError):
            freeze_scenarios(self.db, source_id, TARGET, (("g", ("A",)),))
        with self.assertRaises(KeyError):
            freeze_scenarios(self.db, 999, TARGET, (("g", ("A",)),))
        self.assertEqual(ScenarioStore(self.db).list_ids(), ())

    def test_overlapping_groups_and_duplicate_names(self):
        _, source_id = record_line(self.db, (0, 0, 0), (0, 0, 0))
        groups = (("first", ("A",)), ("second", ("A", "B")))
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, groups)
        frozen = ScenarioStore(self.db).get_scenarios(evidence_id)
        self.assertEqual([g.specimen_ids for g in frozen.groups], [("A",), ("A", "B")])

    def test_target_uses_revision_protocol(self):
        _, source_id = record_line(self.db, (0, 0), (0, 0))
        with self.assertRaises(ValueError):
            freeze_scenarios(self.db, source_id, {"temperature": 0}, (("g", ("A",)),))

    def test_boolean_revision_rejected(self):
        _, source_id = record_line(self.db, (0, 0), (0, 0))
        for bad in (True, 0, -1, 1.0, "1", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    freeze_scenarios(self.db, bad, TARGET, (("g", ("A",)),))
        self.assertEqual(ScenarioStore(self.db).list_ids(), ())


class RobustEngineTests(DatabaseTestCase):
    """The group engine must degrade to the V1 shape when no scenario drops anything."""

    @staticmethod
    def _evidence(rows, target):
        from calibration.design import CalibrationDesign
        from calibration.evidence import build_evidence
        return build_evidence(CalibrationDesign(
            tuple(f"S{index}" for index in range(len(rows))),
            tuple((F(1), F(speed)) for speed, _ in rows) + ((F(1), F(target)),),
            tuple(F(deviation) for _, deviation in rows),
            (F(target),),
        ))

    def test_shapes(self):
        cases = {
            "closed ray": ([(0, -2), (1, -2), (3, -1)], -1, 2, [[None, [-10, 7]]]),
            "singleton": ([(0, -2), (1, -2), (2, -2)], 8, 4, [[[-2, 1], [-2, 1]]]),
            "disconnected": (
                [(0, -2), (1, -2), (2, -1)], 8, 4,
                [[[-37, 8], [-2, 13]], [[4, 5], [79, 29]], [[57, 17], [59, 4]]],
            ),
            "whole line": ([(0, 0), (1, 0)], 0, 1, [[None, None]]),
        }
        for label, (rows, target, k, payload) in cases.items():
            with self.subTest(label=label):
                result = find_robust_candidate_set((self._evidence(rows, target),), k, 1)
                self.assertEqual(result.to_payload(), payload)

    def test_unbounded_ray_from_exclusion(self):
        _, source_id = record_line(self.db, (0, 1, 3, 7), (-2, -2, -1, 5))
        evidence_id = freeze_scenarios(
            self.db, source_id, (-1,), (("drop-D", ("D",)), ("drop-D-alias", ("D",)))
        )
        report = issue_robust(self.db, evidence_id, 2, 2)
        self.assertEqual(report.candidates.to_payload(), [[None, [-10, 7]]])
        self.assertIn(-10, report.candidates)
        self.assertNotIn(1, report.candidates)


class RobustIssueTests(DatabaseTestCase):
    def _frozen_touch(self):
        protocol_id, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        return source_id, freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)

    def test_touch_union_and_intersection(self):
        source_id, evidence_id = self._frozen_touch()
        retire_cohort(self.db, source_id)
        with forbid_source_measurements(self.db):
            wide = issue_robust(self.db, evidence_id, 2, 1)
            point = issue_robust(self.db, evidence_id, 2, 2)
        self.assertEqual(wide.candidates.to_payload(), [[[-1, 1], [5, 1]]])
        self.assertEqual(point.candidates.to_payload(), [[[2, 1], [2, 1]]])
        self.assertEqual(wide.evidence_id, evidence_id)
        self.assertEqual(wide.k, 2)
        self.assertEqual(wide.q, 1)
        self.assertEqual(wide.groups, (("keep-AB", ("C", "D")), ("keep-CD", ("A", "B"))))
        self.assertNotEqual(wide.report_id, point.report_id)

    def test_issue_matches_recompute(self):
        _, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        frozen = ScenarioStore(self.db).get_scenarios(evidence_id)
        evidences = tuple(frozen.group_evidence(g) for g in frozen.groups)
        expected = find_robust_candidate_set(evidences, 2, 1)
        report = issue_robust(self.db, evidence_id, 2, 1)
        self.assertEqual(report.candidates, expected)

    def test_whole_line_and_point(self):
        for speeds, payload in (
            ((-1, 0, 1), [[None, None]]),
            ((-1, -1, 2), [[[0, 1], [0, 1]]]),
        ):
            with self.subTest(speeds=speeds):
                _, source_id = record_line(self.db, speeds, (0, 0, 0))
                evidence_id = freeze_scenarios(self.db, source_id, TARGET, EQUAL_RESPONSE_GROUPS)
                report = issue_robust(self.db, evidence_id, 2, 2)
                self.assertEqual(report.candidates.to_payload(), payload)

    def test_gate_bounds(self):
        _, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        registry = RobustReportRegistry(self.db)
        existing = issue_robust(self.db, evidence_id, 2, 1)
        # Each group holds 2 originals + 1 target, so k is bounded by 3.
        for k, q in ((4, 1), (0, 1), (-1, 1), (True, 1), (2.0, 1), ("2", 1), (None, 1),
                     (2, 3), (2, 0), (2, -1), (2, True), (2, 1.0), (2, "1"), (2, None)):
            with self.subTest(k=k, q=q):
                with self.assertRaises(ValueError):
                    issue_robust(self.db, evidence_id, k, q)
                self.assertEqual(registry.list_ids(), (existing.report_id,))

    def test_gate_shrinks_with_smallest_group(self):
        _, source_id = record_line(self.db, (0, 0, 0, 0), (0, 0, 0, 0))
        groups = (("drop-ABC", ("A", "B", "C")), ("drop-A", ("A",)))
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, groups)
        # Smallest scenario keeps D only: 1 original + target = 2.
        with self.assertRaises(ValueError):
            issue_robust(self.db, evidence_id, 3, 1)
        report = issue_robust(self.db, evidence_id, 2, 2)
        self.assertEqual(report.k, 2)

    def test_unknown_evidence(self):
        _, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        with self.assertRaises(KeyError):
            issue_robust(self.db, evidence_id + 100, 2, 1)
        with self.assertRaises(ValueError):
            issue_robust(self.db, True, 2, 1)
        self.assertEqual(RobustReportRegistry(self.db).list_ids(), ())

    def test_unit_target_independence_of_source(self):
        protocol_id, source_id = record_line(self.db, (0, 0), (0, 0))
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, (("drop-A", ("A",)), ("drop-B", ("B",))))
        child_id = correct_cohort(self.db, source_id, protocol_id, [measurement("A", (0,), 99)])
        with forbid_source_measurements(self.db):
            report = issue_robust(self.db, evidence_id, 1, 1)
        self.assertEqual(report.evidence_id, evidence_id)
        # The corrected revision does not alter the frozen snapshot.
        self.assertEqual(ScenarioStore(self.db).get_scenarios(evidence_id).measurements[0].deviation_um, 0)


class RobustHandoffTests(DatabaseTestCase):
    def _issue(self, k=2, q=2):
        _, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        retire_cohort(self.db, source_id)
        return source_id, evidence_id, issue_robust(self.db, evidence_id, k, q)

    def test_read_after_reopen(self):
        _, evidence_id, report = self._issue()
        self.reopen()
        fixed = read_robust(self.db, report.report_id)
        self.assertEqual(fixed, report)
        self.assertEqual(fixed.groups, (("keep-AB", ("C", "D")), ("keep-CD", ("A", "B"))))
        self.assertEqual(fixed.k, 2)
        self.assertEqual(fixed.q, 2)
        self.assertEqual(fixed.candidates.to_payload(), [[[2, 1], [2, 1]]])

    def test_read_does_not_recompute(self):
        _, _, report = self._issue()
        self.db.execute("DROP TABLE cohort_measurements")
        fixed = read_robust(self.db, report.report_id)
        self.assertEqual(fixed.candidates.to_payload(), [[[2, 1], [2, 1]]])

    def test_unknown_report(self):
        _, _, report = self._issue()
        with self.assertRaises(KeyError):
            read_robust(self.db, report.report_id + 100)
        for bad in (True, 0, -1, "1", 1.0, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    read_robust(self.db, bad)

    def test_reports_are_distinct_and_relations_preserved(self):
        _, evidence_id, point = self._issue(2, 2)
        wide = issue_robust(self.db, evidence_id, 2, 1)
        self.assertEqual(read_robust(self.db, point.report_id), point)
        self.assertEqual(read_robust(self.db, wide.report_id), wide)
        self.assertNotEqual(point.report_id, wide.report_id)

    def test_v1_and_robust_coexist(self):
        from calibration.publish import freeze_calibration
        protocol_id, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        calibration_id = freeze_calibration(self.db, source_id, TARGET)
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        v1 = issue_report(self.db, calibration_id, 2)
        robust = issue_robust(self.db, evidence_id, 2, 2)
        self.assertEqual(read_report(self.db, v1.report_id), v1)
        self.assertEqual(read_robust(self.db, robust.report_id), robust)
        self.assertEqual(RobustReportRegistry(self.db).list_ids(), (robust.report_id,))

    def test_reinitialize_preserves_frozen_and_reports(self):
        _, evidence_id, report = self._issue()
        expected = ScenarioStore(self.db).get_scenarios(evidence_id)
        initialize_database(self.db)
        initialize_database(self.db)
        self.reopen()
        self.assertEqual(ScenarioStore(self.db).get_scenarios(evidence_id), expected)
        self.assertEqual(read_robust(self.db, report.report_id), report)


class RobustAtomicityTests(DatabaseTestCase):
    def test_freeze_rolls_back_and_retries(self):
        _, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        store = ScenarioStore(self.db)
        # A rejected target after validation-order checks leaves nothing behind.
        with self.assertRaises(ValueError):
            freeze_scenarios(self.db, source_id, TARGET, (("g", ("A",)), ("g", ("B",))))
        self.assertEqual(store.list_ids(), ())
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        self.assertEqual(store.list_ids(), (evidence_id,))

    def test_issue_rolls_back_and_retries(self):
        _, source_id = record_line(self.db, TOUCH_SPEEDS, TOUCH_DEVIATIONS)
        evidence_id = freeze_scenarios(self.db, source_id, TARGET, TOUCH_GROUPS)
        retire_cohort(self.db, source_id)
        registry = RobustReportRegistry(self.db)
        with self.assertRaises(CommitBlocked):
            issue_robust(self.db, evidence_id, 2, 2, before_commit=block_commit)
        self.assertEqual(registry.list_ids(), ())
        self.reopen()
        self.assertEqual(RobustReportRegistry(self.db).list_ids(), ())
        retried = issue_robust(self.db, evidence_id, 2, 2)
        self.assertEqual(RobustReportRegistry(self.db).list_ids(), (retried.report_id,))
        self.assertEqual(retried.candidates.to_payload(), [[[2, 1], [2, 1]]])
