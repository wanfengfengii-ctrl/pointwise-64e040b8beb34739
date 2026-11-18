import sqlite3
from collections.abc import Iterable, Mapping

from cohort.intake import collect_measurements
from cohort.records import CohortRevision, SpecimenMeasurement
from cohort.store import CohortStore
from handoff.transactions import write_transaction
from protocol.catalog import ProtocolCatalog


def apply_corrections(
    parent: CohortRevision, corrections: tuple[SpecimenMeasurement, ...]
) -> tuple[SpecimenMeasurement, ...]:
    replacements = {measurement.specimen_id: measurement for measurement in corrections}
    parent_ids = {measurement.specimen_id for measurement in parent.measurements}
    unknown = replacements.keys() - parent_ids
    if unknown:
        raise ValueError(f"corrections refer to unknown specimens {sorted(unknown)!r}")
    return tuple(
        replacements.get(measurement.specimen_id, measurement)
        for measurement in parent.measurements
    )


def correct_cohort(
    connection: sqlite3.Connection,
    parent_revision_id: int,
    protocol_id: int,
    rows: Iterable[Mapping[str, object]],
) -> int:
    store = CohortStore(connection)
    with write_transaction(connection):
        parent = store.require_available(parent_revision_id)
        if protocol_id != parent.protocol_id:
            raise ValueError("the correction must use the parent's protocol revision")
        protocol = ProtocolCatalog(connection).get_protocol(parent.protocol_id)
        corrections = collect_measurements(protocol, rows)
        measurements = apply_corrections(parent, corrections)
        revision_id = store.insert_revision(parent.protocol_id, parent.revision_id, measurements)
    return revision_id
