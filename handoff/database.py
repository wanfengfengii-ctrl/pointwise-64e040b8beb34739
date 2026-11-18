import sqlite3
from pathlib import Path
from typing import Union

from calibration.store import create_calibration_schema
from cohort.store import create_cohort_schema
from handoff.registry import create_report_schema
from handoff.transactions import write_transaction
from protocol.catalog import create_protocol_schema


def initialize_database(connection: sqlite3.Connection) -> None:
    with write_transaction(connection):
        create_protocol_schema(connection)
        create_cohort_schema(connection)
        create_calibration_schema(connection)
        create_report_schema(connection)


def open_database(path: Union[str, Path]) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        initialize_database(connection)
    except BaseException:
        connection.close()
        raise
    return connection
