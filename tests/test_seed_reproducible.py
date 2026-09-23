"""
Phase 8: seeding a fresh database from the seed scripts must reproduce the
committed full_text exactly — a permanent guard that the verbatim text in
data/act_verbatim_2026-09-23.json (and the Rules seed script) stays in
sync with what's actually in db/dpdpa.db. Reads the live database (never
writes to it) to compare against; all writes in this file go to a
pytest-managed scratch file.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db as db_module
import seed_dpdp_act_full as seed_act

LIVE_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "dpdpa.db"


def test_seeding_act_reproduces_committed_full_text(tmp_path):
    scratch_path = tmp_path / "seed_act_test.db"
    seed_act.main(db_path=scratch_path)

    scratch_conn = db_module.get_connection(scratch_path)
    live_conn = db_module.get_connection(LIVE_DB_PATH)  # read-only use

    scratch_rows = {
        r["provision_id"]: r["full_text"]
        for r in scratch_conn.execute(
            "SELECT provision_id, full_text FROM provisions WHERE provision_id LIKE 'DPDPA-%'"
        )
    }
    live_rows = {
        r["provision_id"]: r["full_text"]
        for r in live_conn.execute(
            "SELECT provision_id, full_text FROM provisions WHERE provision_id LIKE 'DPDPA-%'"
        )
    }
    scratch_conn.close()
    live_conn.close()

    assert scratch_rows.keys() == live_rows.keys(), (
        f"provision_id sets differ: only in scratch={scratch_rows.keys() - live_rows.keys()}, "
        f"only in live={live_rows.keys() - scratch_rows.keys()}"
    )
    mismatches = [pid for pid in scratch_rows if scratch_rows[pid] != live_rows[pid]]
    assert mismatches == [], f"full_text mismatch for: {mismatches}"
