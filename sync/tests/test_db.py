"""Price-history pruning. Run from sync/: uv run --frozen --with pytest python -m pytest tests -q"""
import sqlite3
from pathlib import Path

from app.db import prune_price_history

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def test_prune_keeps_the_price_each_model_had_when_the_window_opens():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text())
    conn.executemany(
        "INSERT INTO model_price_history (model_id, input_per_mtok, recorded_at) VALUES (?,?,?)",
        [("a", 3.0, "2026-08-01"), ("a", 2.5, "2026-09-01"), ("a", 2.0, "2026-10-20"),  # moved since
         ("b", 1.0, "2026-07-01"),  # stable for months: its only row is old
         ("c", 5.0, "2026-10-10")])  # first seen inside the window
    prune_price_history(conn, "2026-09-26")
    assert conn.execute("SELECT model_id, input_per_mtok FROM model_price_history "
                        "ORDER BY model_id, recorded_at").fetchall() == [
        ("a", 2.5), ("a", 2.0), ("b", 1.0), ("c", 5.0)]
