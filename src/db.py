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
    _migrate_change_origin(conn)
    conn.commit()


def _migrate_change_origin(conn: sqlite3.Connection) -> None:
    """
    Idempotent migration: add change_log.change_origin if it doesn't exist yet.
    SQLite has no 'ADD COLUMN IF NOT EXISTS', so we check PRAGMA table_info first.
    Safe to call on every startup, including on a brand-new DB where the CREATE
    TABLE above already included the column.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(change_log)").fetchall()}
    if "change_origin" not in cols:
        conn.execute(
            "ALTER TABLE change_log ADD COLUMN change_origin TEXT "
            "CHECK (change_origin IN ('baseline','regulatory','data_correction'))"
        )


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
