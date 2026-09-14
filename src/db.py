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
    conn.commit()


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
