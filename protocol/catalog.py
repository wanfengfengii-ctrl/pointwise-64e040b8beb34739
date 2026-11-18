import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from handoff.transactions import write_transaction
from protocol.covariates import CovariateOrder, make_covariate_order
from protocol.units import MICROMETRE
from protocol.validation import validate_protocol_definition


@dataclass(frozen=True)
class ProtocolRevision:
    revision_id: int
    name: str
    covariates: CovariateOrder
    deviation_unit: str


def create_protocol_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS protocol_revisions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            covariates TEXT NOT NULL,
            deviation_unit TEXT NOT NULL
        )
        """
    )


class ProtocolCatalog:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def insert_revision(
        self, name: str, order: CovariateOrder, deviation_unit: str
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO protocol_revisions (name, covariates, deviation_unit) VALUES (?, ?, ?)",
            (name, json.dumps(order.names, ensure_ascii=False), deviation_unit),
        )
        return cursor.lastrowid

    def get_protocol(self, revision_id: int) -> ProtocolRevision:
        row = self.connection.execute(
            "SELECT id, name, covariates, deviation_unit FROM protocol_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown protocol revision {revision_id}")
        identifier, name, covariates, unit = row
        return ProtocolRevision(identifier, name, make_covariate_order(json.loads(covariates)), unit)

    def list_ids(self) -> tuple[int, ...]:
        return tuple(row[0] for row in self.connection.execute(
            "SELECT id FROM protocol_revisions ORDER BY id"
        ))


def register_protocol(
    connection: sqlite3.Connection,
    name: str,
    covariates: Sequence[str],
    deviation_unit: str = MICROMETRE,
) -> int:
    order, unit = validate_protocol_definition(name, covariates, deviation_unit)
    with write_transaction(connection):
        revision_id = ProtocolCatalog(connection).insert_revision(name, order, unit)
    return revision_id
