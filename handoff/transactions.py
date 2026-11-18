import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Optional


@contextmanager
def write_transaction(
    connection: sqlite3.Connection, *, before_commit: Optional[Callable[[], None]] = None
) -> Iterator[None]:
    """Order writers, then commit the complete body or roll back the write."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        if before_commit is not None:
            before_commit()
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
