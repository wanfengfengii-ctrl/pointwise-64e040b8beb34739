import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from calibration.publish import freeze_calibration
from cohort.intake import record_cohort
from cohort.retirement import retire_cohort
from cohort.revisions import correct_cohort
from cohort.store import CohortStore
from handoff.database import open_database
from handoff.export import export_report
from handoff.lookup import read_report
from protocol.catalog import register_protocol
from review.issue import issue_report


def main() -> None:
    sample_path = Path(__file__).with_name("sample.json")
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "lab.sqlite3"
        with closing(open_database(database_path)) as db:
            protocol_id = register_protocol(db, **sample["protocol"])
            source_id = record_cohort(db, protocol_id, sample["measurements"])
            corrected_id = correct_cohort(db, source_id, protocol_id, sample["corrections"])
            store = CohortStore(db)
            original, corrected = store.get_revision(source_id), store.get_revision(corrected_id)
            print(json.dumps({
                "初始修订": original.revision_id,
                "初始偏差微米": {row.specimen_id: str(row.deviation_um) for row in original.measurements},
                "更正修订": corrected.revision_id,
                "更正父版": corrected.parent_revision_id,
                "更正偏差微米": {row.specimen_id: str(row.deviation_um) for row in corrected.measurements},
            }, ensure_ascii=False, sort_keys=True))
            calibration_id = freeze_calibration(db, source_id, sample["target_conditions"])
            original_report = issue_report(db, calibration_id, sample["threshold"])
            original_export = export_report(db, original_report.report_id)
            retire_cohort(db, source_id)

        with closing(open_database(database_path)) as db:
            original = read_report(db, original_report.report_id)
            reopened_export = export_report(db, original.report_id)
            renewed = issue_report(db, original.calibration_id, sample["handoff_threshold"])
            print(json.dumps({
                "原来源已停用": CohortStore(db).get_revision(source_id).retired,
                "重开领取": json.loads(reopened_export),
                "续签报告": json.loads(export_report(db, renewed.report_id)),
                "原报告导出保全": original_export == export_report(db, original.report_id),
            }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
