import sqlite3

from calibration.design import build_design
from calibration.evidence import build_evidence
from calibration.store import CalibrationStore
from cohort.store import CohortStore
from handoff.transactions import write_transaction
from protocol.catalog import ProtocolCatalog
from protocol.covariates import ConditionInput


def freeze_calibration(
    connection: sqlite3.Connection, source_revision_id: int, target_conditions: ConditionInput
) -> int:
    # A retirement on another connection must commit either before this check or after publication.
    with write_transaction(connection):
        cohort = CohortStore(connection).require_available(source_revision_id)
        protocol = ProtocolCatalog(connection).get_protocol(cohort.protocol_id)
        design = build_design(cohort, protocol, target_conditions)
        evidence = build_evidence(design)
        calibration_id = CalibrationStore(connection).insert_calibration(
            cohort.revision_id, protocol.revision_id, design.target_conditions, evidence
        )
    return calibration_id
