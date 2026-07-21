"""Read-only SQLite access. The BE can never mutate the catalog (mode=ro)."""
import sqlite3
from collections.abc import Iterator

from app.settings import settings


def _connect() -> sqlite3.Connection:
    # mode=ro: opening read-only means a bug or injection can't write the catalog.
    conn = sqlite3.connect(f"file:{settings.DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency - one connection per request."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()
