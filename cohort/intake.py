import sqlite3
from collections.abc import Iterable, Mapping

from cohort.records import SpecimenMeasurement, build_measurement
from cohort.store import CohortStore
from handoff.transactions import write_transaction
from protocol.catalog import ProtocolCatalog, ProtocolRevision


MEASUREMENT_FIELDS = {"specimen_id", "conditions", "deviation_um"}


def collect_measurements(
    protocol: ProtocolRevision, rows: Iterable[Mapping[str, object]]
) -> tuple[SpecimenMeasurement, ...]:
    try:
        row_iterator = iter(rows)
    except TypeError as error:
        raise ValueError("expected a collection of measurement rows") from error

    measurements = []
    seen = set()
    for row in row_iterator:
        if not isinstance(row, Mapping) or row.keys() != MEASUREMENT_FIELDS:
            raise ValueError("a measurement needs specimen_id, conditions, and deviation_um")
        measurement = build_measurement(
            protocol, row["specimen_id"], row["conditions"], row["deviation_um"]
        )
        if measurement.specimen_id in seen:
            raise ValueError(f"duplicate specimen id {measurement.specimen_id!r}")
        seen.add(measurement.specimen_id)
        measurements.append(measurement)

    if not measurements:
        raise ValueError("a cohort or correction must contain a measurement")
    return tuple(measurements)


def record_cohort(
    connection: sqlite3.Connection, protocol_id: int, rows: Iterable[Mapping[str, object]]
) -> int:
    protocol = ProtocolCatalog(connection).get_protocol(protocol_id)
    measurements = collect_measurements(protocol, rows)
    with write_transaction(connection):
        revision_id = CohortStore(connection).insert_revision(protocol_id, None, measurements)
    return revision_id
