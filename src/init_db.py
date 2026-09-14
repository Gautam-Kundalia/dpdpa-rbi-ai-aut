"""
Initialize db/dpdpa.db from schema.sql.

Usage:
    python src/init_db.py

Then load real data:
    python src/seed_dpdp_rules_full.py
    python src/seed_dpdp_act_full.py
    python src/export_word.py
    python src/export_excel.py
"""
from __future__ import annotations

from db import DB_PATH, get_connection, init_schema


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_schema(conn)
    conn.close()
    print(f"Initialized {DB_PATH} with schema (empty).")


if __name__ == "__main__":
    main()
