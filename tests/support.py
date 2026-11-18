import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from calibration.publish import freeze_calibration
from cohort.intake import record_cohort
from handoff.database import open_database
from protocol.catalog import register_protocol


def measurement(specimen_id, conditions, deviation_um):
    return {"specimen_id": specimen_id, "conditions": conditions, "deviation_um": deviation_um}


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "lab.sqlite3"
        self.db = open_database(self.path)
        self.addCleanup(lambda: self.db.close())

    def reopen(self):
        self.db.close()
        self.db = open_database(self.path)

    def line_cohort(self, speeds=(0, 0), deviations=(-1, 1)):
        protocol_id = register_protocol(self.db, "line coating", ["line_speed"])
        rows = [
            measurement(chr(ord("A") + index), (speed,), deviation)
            for index, (speed, deviation) in enumerate(zip(speeds, deviations))
        ]
        return protocol_id, record_cohort(self.db, protocol_id, rows)

    def freeze_line(self, speeds, deviations, target):
        protocol_id, source_id = self.line_cohort(speeds, deviations)
        return protocol_id, source_id, freeze_calibration(self.db, source_id, (target,))


def emit_scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    document = {
        "case_id": case_id,
        "input": inputs,
        "expected": expected,
        "actual": actual,
        "downstream_expected": downstream_expected,
        "downstream_actual": downstream_actual,
        "code_paths": code_paths,
        "oracle": oracle,
    }
    print("POINTWISE_SCENARIO " + json.dumps(document, ensure_ascii=False, sort_keys=True), flush=True)
