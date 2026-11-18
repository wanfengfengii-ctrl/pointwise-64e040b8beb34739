import sqlite3

from cohort.store import CohortStore
from handoff.transactions import write_transaction


def retire_cohort(connection: sqlite3.Connection, revision_id: int) -> None:
    with write_transaction(connection):
        CohortStore(connection).mark_retired(revision_id)
