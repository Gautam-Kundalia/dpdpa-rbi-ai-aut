"""
Thin SQLite helper for the DPDP Rules tracker.

Everything else in this project (fetchers, classifiers, the Excel exporter)
should go through this module rather than opening sqlite3 connections
directly, so we have one place that knows the DB path and schema.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "dpdpa.db"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a connection with sane defaults (foreign keys on, dict-like rows)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    """Create tables if they don't exist yet. Safe to call every run."""
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    _run_migrations(conn)
    conn.commit()


# Every migration this project has ever needed, as (table, column, the rest of
# the ALTER TABLE statement). All of them are ADDITIVE — a new column with a
# default — so an old database upgrades in place and no existing row is touched.
# SQLite has no "ADD COLUMN IF NOT EXISTS", so each one is applied only when
# PRAGMA table_info says it is missing. Safe to call on every startup, including
# on a brand-new database where the CREATE TABLE statements already include them.
MIGRATIONS: list[tuple[str, str, str]] = [
    # 23 Sep 2026: tells a real government change apart from a fix to our own data.
    ("change_log", "change_origin",
     "TEXT CHECK (change_origin IN ('baseline','regulatory','data_correction'))"),
    # 30 Sep 2026 (audit M-5): is this source still being watched, or is it a
    # frozen relic kept only for its change history? The Excel Source_Log sheet
    # claims to show "what is being watched right now", which was untrue.
    ("source_log", "watched", "INTEGER NOT NULL DEFAULT 1"),
    # 30 Sep 2026 (audit M-3): how long the SAME fetch problem has been going on,
    # so a source that has been down for a week stops shouting on the subject
    # line every single day while still being listed in the email body.
    ("source_log", "error_signature", "TEXT"),
    ("source_log", "error_streak_days", "INTEGER NOT NULL DEFAULT 0"),
    ("source_log", "error_streak_last_date", "TEXT"),
]


def _run_migrations(conn: sqlite3.Connection) -> None:
    for table, column, ddl in MIGRATIONS:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def next_id(conn: sqlite3.Connection, table: str, id_col: str, prefix: str) -> str:
    """
    Generate the next sequential ID for a table, e.g. 'CHG-0007'.
    Assumes IDs are always '<prefix>-<4-digit-number>'.
    """
    cur = conn.execute(f"SELECT {id_col} FROM {table} WHERE {id_col} LIKE ?", (f"{prefix}-%",))
    max_n = 0
    for row in cur.fetchall():
        try:
            n = int(row[id_col].split("-")[-1])
            max_n = max(max_n, n)
        except (ValueError, IndexError):
            continue
    return f"{prefix}-{max_n + 1:04d}"
