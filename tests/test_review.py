from fractions import Fraction as F

from calibration.evidence import AffineResidual, FrozenEvidence
from calibration.publish import freeze_calibration
from calibration.store import CalibrationStore
from cohort.retirement import retire_cohort
from cohort.revisions import correct_cohort
from handoff.lookup import read_report
from handoff.registry import ReportRegistry
from handoff.transactions import write_transaction
from review.comparison import count_qualifying_specimens
from review.issue import issue_report
from review.region_set import CandidateSet, ClosedRegion
from tests.support import DatabaseTestCase, emit_scenario, measurement


THICKNESS_SET_MISMATCH = "THICKNESS_SET_MISMATCH"


class ReviewTests(DatabaseTestCase):
    def test_full_rank(self):
        protocol_id, source_id, calibration_id = self.freeze_line((0, 1, 2), (0, 1, 2), 3)
        report = issue_report(self.db, calibration_id, 1)
        self.assertEqual(report.calibration_id, calibration_id)
        self.assertEqual(report.protocol_id, protocol_id)
        self.assertEqual(report.source_revision_id, source_id)
        self.assertEqual(report.threshold, 1)
        self.assertEqual(report.candidates.regions, (ClosedRegion(None, None),))
        self.assertEqual(read_report(self.db, report.report_id), report)

    def test_rational_projection(self):
        _, source_id, calibration_id = self.freeze_line((0, 1, 2), (0, 1, 2), 3)
        calibration = CalibrationStore(self.db).get_calibration(calibration_id)
        self.assertEqual(calibration.source_revision_id, source_id)
        self.assertEqual(calibration.target_conditions, (3,))
        # The intercept is -1/5 and the line-speed coefficient is 13/10.
        expected = (F(1, 5), F(-1, 10), F(-2, 5), F(3, 10))
        self.assertEqual(calibration.evidence.residuals_at(4), expected)

    def test_invalid_target(self):
        _, source_id, calibration_id = self.freeze_line((0, 1, 2), (0, 1, 2), 3)
        with self.assertRaises(ValueError):
            freeze_calibration(self.db, source_id, ())
        with self.assertRaises(ValueError):
            freeze_calibration(self.db, source_id, {"temperature": 3})
        self.assertEqual(CalibrationStore(self.db).list_ids(), (calibration_id,))

    def test_closed_ray(self):
        _, _, calibration_id = self.freeze_line((0, 1, 3), (-2, -2, -1), -1)
        result = issue_report(self.db, calibration_id, 2).candidates
        self.assertEqual(result.regions, (ClosedRegion(None, F(-10, 7)),))
        self.assertIn(F(-10, 7), result)
        self.assertIn(-10, result)
        self.assertNotIn(F(-10, 7) + F(1, 100), result)

    def test_rank_deficient(self):
        _, source_id, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        retire_cohort(self.db, source_id)
        report = issue_report(self.db, calibration_id, 2)
        actual = report.candidates.to_payload()
        expected = [[[-3, 1], [3, 1]]]
        self.assertEqual(actual, expected, THICKNESS_SET_MISMATCH)
        released = read_report(self.db, report.report_id)
        self.assertEqual(released, report)
        membership = [candidate in released.candidates for candidate in (2, 3, 4)]
        self.assertEqual(membership, [True, True, False], THICKNESS_SET_MISMATCH)
        emit_scenario(
            "rank_deficient",
            {"original_speeds": [0, 0], "deviations_um": [-1, 1], "target_speed": 0, "k": 2, "source_retired": True},
            expected,
            actual,
            [True, True, False],
            membership,
            ["calibration/publish.py", "calibration/evidence.py", "review/regions.py", "handoff/lookup.py"],
            "The common fitted value is t/3. Comparing the two original residual magnitudes with |2t/3| yields [-3,3]. Membership witnesses are 2, 3, and 4.",
        )

    def test_selected_revision(self):
        protocol_id, parent_id = self.line_cohort()
        child_id = correct_cohort(self.db, parent_id, protocol_id, [measurement("A", (0,), -2)])
        old_calibration = freeze_calibration(self.db, parent_id, (0,))
        new_calibration = freeze_calibration(self.db, child_id, (0,))
        original = issue_report(self.db, old_calibration, 2)
        corrected = issue_report(self.db, new_calibration, 2)
        self.assertEqual((original.calibration_id, original.source_revision_id), (old_calibration, parent_id))
        self.assertEqual((corrected.calibration_id, corrected.source_revision_id), (new_calibration, child_id))
        self.assertEqual(original.candidates.regions, (ClosedRegion(-3, 3),))
        self.assertEqual(corrected.candidates.regions, (ClosedRegion(-5, 4),))
        self.assertEqual(read_report(self.db, original.report_id), original)

    def test_residual_response(self):
        _, source_id, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        retire_cohort(self.db, source_id)
        evidence = CalibrationStore(self.db).get_calibration(calibration_id).evidence
        self.assertEqual(tuple(specimen_id for specimen_id, _ in evidence.originals), ("A", "B"))
        examples = {
            0: (F(-1), F(1), F(0)),
            2: (F(-5, 3), F(1, 3), F(4, 3)),
            3: (F(-2), F(0), F(2)),
        }
        for candidate, expected in examples.items():
            with self.subTest(candidate=candidate):
                self.assertEqual(evidence.residuals_at(candidate), expected, THICKNESS_SET_MISMATCH)
        self.assertEqual(count_qualifying_specimens(evidence, F(2)), 2)

    def test_tie_boundary(self):
        protocol_id, source_id = self.line_cohort()
        evidence = FrozenEvidence(
            (("A", AffineResidual(F(-1), F(-1, 3))), ("B", AffineResidual(F(1), F(-1, 3)))),
            AffineResidual(F(0), F(2, 3)),
        )
        with write_transaction(self.db):
            calibration_id = CalibrationStore(self.db).insert_calibration(source_id, protocol_id, (F(0),), evidence)
        retire_cohort(self.db, source_id)
        result = issue_report(self.db, calibration_id, 2).candidates
        for boundary in (-3, 3):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, result, THICKNESS_SET_MISMATCH)
        self.assertEqual(result.regions, (ClosedRegion(-3, 3),), THICKNESS_SET_MISMATCH)

    def test_singleton(self):
        _, _, calibration_id = self.freeze_line((0, 1, 2), (-2, -2, -2), 8)
        report = issue_report(self.db, calibration_id, 4)
        self.assertEqual(report.candidates.regions, (ClosedRegion(-2, -2),))
        self.assertIn(-2, report.candidates)
        self.assertNotIn(F(-201, 100), report.candidates)
        self.assertNotIn(F(-199, 100), report.candidates)
        self.assertEqual(read_report(self.db, report.report_id), report)

    def test_disconnected(self):
        _, _, calibration_id = self.freeze_line((0, 1, 2), (-2, -2, -1), 8)
        report = issue_report(self.db, calibration_id, 4)
        expected = [[[-37, 8], [-2, 13]], [[4, 5], [79, 29]], [[57, 17], [59, 4]]]
        actual = report.candidates.to_payload()
        self.assertEqual(actual, expected)
        stored = read_report(self.db, report.report_id)
        self.assertEqual(stored, report)
        membership = [candidate in stored.candidates for candidate in (0, 3)]
        self.assertEqual(membership, [False, False])
        emit_scenario(
            "singleton.disconnected",
            {"original_speeds": [0, 1, 2], "deviations_um": [-2, -2, -1], "target_speed": 8, "k": 4},
            expected,
            actual,
            [False, False],
            membership,
            ["calibration/least_squares.py", "review/comparison.py", "review/regions.py", "handoff/registry.py"],
            "The fitted line for candidate t has intercept (-154-13t)/155 and slope (113+21t)/155. Intersect the three absolute-residual comparisons and check 0 and 3 in the gaps.",
        )

    def test_empty_representation(self):
        empty = CandidateSet(())
        whole = CandidateSet((ClosedRegion(0, None), ClosedRegion(None, 0)))
        self.assertEqual(empty.to_payload(), [])
        self.assertEqual(whole.regions, (ClosedRegion(None, None),))
        self.assertEqual(whole.to_payload(), [[None, None]])
        self.assertEqual(CandidateSet.from_payload([]), empty)
        self.assertEqual(CandidateSet.from_payload([[None, None]]), whole)
        self.assertNotIn(0, empty)
        self.assertIn(0, whole)

    def test_bad_k(self):
        _, _, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        registry = ReportRegistry(self.db)
        existing = issue_report(self.db, calibration_id, 1)
        for k in (4, 0, -1, True, 1.0, "2", None):
            with self.subTest(k=k):
                with self.assertRaisesRegex(ValueError, "k must be an integer from 1 to 3"):
                    issue_report(self.db, calibration_id, k)
                self.assertEqual(registry.list_ids(), (existing.report_id,))

    def test_limit_includes_target(self):
        _, _, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        report = issue_report(self.db, calibration_id, 3)
        self.assertEqual(report.threshold, 3)
        self.assertEqual(report.candidates.regions, (ClosedRegion(-1, 1),))
        self.assertEqual(read_report(self.db, report.report_id), report)

    def test_missing_calibration(self):
        _, _, calibration_id = self.freeze_line((0, 0), (-1, 1), 0)
        with self.assertRaisesRegex(KeyError, "unknown calibration"):
            issue_report(self.db, calibration_id + 100, 2)
        self.assertEqual(ReportRegistry(self.db).list_ids(), ())
