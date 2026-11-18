import sqlite3

from calibration.design import build_design
from calibration.evidence import build_evidence
from calibration.scenarios import ScenarioStore, validate_scenario_groups
from calibration.store import CalibrationStore
from cohort.store import CohortStore
from handoff.transactions import write_transaction
from protocol.catalog import ProtocolCatalog
from protocol.covariates import ConditionInput
from protocol.identifiers import require_business_id


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


def freeze_scenarios(
    connection: sqlite3.Connection,
    revision_id: int,
    target_conditions: ConditionInput,
    groups: object,
) -> int:
    """Freeze named exclusion scenarios against an available source revision."""
    require_business_id(revision_id, "revision id")
    with write_transaction(connection):
        cohort = CohortStore(connection).require_available(revision_id)
        protocol = ProtocolCatalog(connection).get_protocol(cohort.protocol_id)
        design = build_design(cohort, protocol, target_conditions)
        scenarios = validate_scenario_groups(cohort, groups)
        return ScenarioStore(connection).insert_scenarios(
            cohort.revision_id,
            protocol.revision_id,
            design.target_conditions,
            scenarios,
            cohort.measurements,
        )
