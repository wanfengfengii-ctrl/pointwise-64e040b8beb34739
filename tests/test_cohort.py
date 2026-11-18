from fractions import Fraction

from cohort.intake import record_cohort
from cohort.revisions import correct_cohort
from cohort.store import CohortStore
from protocol.catalog import ProtocolCatalog, register_protocol
from tests.support import DatabaseTestCase, measurement


class CohortTests(DatabaseTestCase):
    def test_revision(self):
        protocol_id, parent_id = self.line_cohort()
        store = CohortStore(self.db)
        parent = store.get_revision(parent_id)
        self.assertEqual(
            [(row.specimen_id, row.conditions, row.deviation_um) for row in parent.measurements],
            [("A", (0,), -1), ("B", (0,), 1)],
        )
        child_id = correct_cohort(self.db, parent_id, protocol_id, [measurement("A", (0,), -2)])
        child = store.get_revision(child_id)
        self.assertNotEqual(child_id, parent_id)
        self.assertIsNone(parent.parent_revision_id)
        self.assertEqual(child.parent_revision_id, parent_id)
        self.assertEqual(child.protocol_id, protocol_id)
        self.assertEqual([(row.specimen_id, row.deviation_um) for row in child.measurements], [("A", -2), ("B", 1)])
        self.assertEqual(child.measurements[1], parent.measurements[1])
        self.assertEqual(store.get_revision(parent_id), parent)

    def test_coordinate_order(self):
        coordinate_order = ("line_speed", "cure_temperature")
        protocol_id = register_protocol(self.db, "two coordinates", coordinate_order, "µm")
        catalog = ProtocolCatalog(self.db)
        self.assertEqual(catalog.get_protocol(protocol_id).covariates.names, coordinate_order)
        self.assertEqual(catalog.get_protocol(protocol_id).deviation_unit, "um")
        initial = [
            measurement("A", {"cure_temperature": 7, "line_speed": 2}, "-1/2"),
            measurement("B", (3, 11), "1.25"),
        ]
        parent_id = record_cohort(self.db, protocol_id, initial)
        child_id = correct_cohort(
            self.db, parent_id, protocol_id, [measurement("A", (2, 7), "-3/2")]
        )
        store = CohortStore(self.db)
        parent, child = store.get_revision(parent_id), store.get_revision(child_id)
        self.assertEqual(tuple(row.conditions for row in parent.measurements), ((2, 7), (3, 11)))
        self.assertEqual(tuple(row.conditions for row in child.measurements), ((2, 7), (3, 11)))
        self.assertEqual(parent.measurements[0].deviation_um, Fraction(-1, 2))
        self.assertEqual(child.measurements[0].deviation_um, Fraction(-3, 2))
        self.assertEqual(child.measurements[1].deviation_um, Fraction(5, 4))
        self.assertEqual(child.parent_revision_id, parent_id)
        self.assertEqual(child.protocol_id, protocol_id)

    def test_invalid_protocol(self):
        registered = register_protocol(self.db, "valid", ["line_speed"])
        catalog = ProtocolCatalog(self.db)
        cases = [
            ("duplicate", ["line_speed", "line_speed"], "um"),
            ("no coordinates", [], "um"),
            ("too many", ["a", "b", "c", "d", "e"], "um"),
            ("bad unit", ["line_speed"], "mm"),
        ]
        for name, coordinates, unit in cases:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    register_protocol(self.db, name, coordinates, unit)
                self.assertEqual(catalog.list_ids(), (registered,))

    def test_invalid_correction(self):
        protocol_id, parent_id = self.line_cohort()
        alternative = register_protocol(self.db, "other protocol", ["line_speed"])
        store = CohortStore(self.db)
        original = store.get_revision(parent_id)
        with self.assertRaisesRegex(ValueError, "parent's protocol"):
            correct_cohort(self.db, parent_id, alternative, [measurement("A", (0,), -4)])
        with self.assertRaisesRegex(ValueError, "unknown specimens"):
            correct_cohort(self.db, parent_id, protocol_id, [measurement("C", (0,), -4)])
        self.assertEqual(store.list_ids(), (parent_id,))
        self.assertEqual(store.get_revision(parent_id), original)

    def test_duplicate(self):
        protocol_id, initial_id = self.line_cohort()
        with self.assertRaisesRegex(ValueError, "duplicate specimen"):
            record_cohort(self.db, protocol_id, [measurement("X", (2,), 1), measurement("X", (3,), 2)])
        self.assertEqual(CohortStore(self.db).list_ids(), (initial_id,))

    def test_invalid_measurement(self):
        protocol_id, initial_id = self.line_cohort()
        store = CohortStore(self.db)
        invalid_rows = [
            measurement("B", {"temperature": 2}, 1),
            measurement("B", (None,), 1),
            measurement("B", (2,), None),
            measurement("B", (2,), True),
            measurement("B", (2,), 0.25),
            measurement("B", (2,), "1/0"),
        ]
        for bad_row in invalid_rows:
            with self.subTest(row=bad_row):
                with self.assertRaises(ValueError):
                    record_cohort(self.db, protocol_id, [measurement("A", (0,), 1), bad_row])
                self.assertEqual(store.list_ids(), (initial_id,))
        with self.assertRaises(KeyError):
            record_cohort(self.db, protocol_id + 100, [measurement("A", (0,), 1)])
        self.assertEqual(store.list_ids(), (initial_id,))
