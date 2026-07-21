"""SQLite connection + schema init for the Impulse catalog."""
import sqlite3

from app.settings import settings


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # the BE (reader) doesn't block the sync's write txn
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indexes + seed reference data if absent (idempotent)."""
    conn.executescript(settings.SCHEMA_PATH.read_text())


def wipe_catalog(conn: sqlite3.Connection) -> None:
    """
    Clear the rebuilt catalog (inside the caller's txn). Deleting `models` and
    `providers` cascades their child tables. Reference data (capabilities,
    licenses) and the price-history LOG are intentionally preserved.
    """
    conn.execute("DELETE FROM models")     # cascades all model_* children
    conn.execute("DELETE FROM providers")  # cascades all provider_* children
    conn.execute("DELETE FROM meta")
