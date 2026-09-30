"""
The three one-off data-fix scripts from the 30 September 2026 audit.

H-5   scripts/fix_corrigendum_schedules_2026-09-30.py — records corrigendum
      G.S.R. 892(E) items (iv) and (v) as GOVERNMENT changes, so they are
      highlighted and reported instead of looking like our own typo fix.
H-7 } scripts/restore_verbatim_wording_2026-09-30.py — puts back the Seventh
M-11} Schedule's paraphrased wording and the 15 missing heading dashes.
M-5   scripts/mark_unwatched_sources_2026-09-30.py — marks the four retired
      source_log rows as no longer watched.

Every test here runs against a THROWAWAY COPY of the committed database under
pytest's tmp_path. Nothing touches db/dpdpa.db.

What each script must prove, because these are the properties that make a
one-off script safe for somebody who is not a developer to run:

  1. a dry run (no --apply) changes NOTHING;
  2. --apply changes exactly the rows it said it would, and nothing else;
  3. running --apply twice is safe — the second run says "nothing to do".

No network. No AI calls.
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_DB = REPO_ROOT / "db" / "dpdpa.db"
SCRIPTS = REPO_ROOT / "scripts"

# The two wording scripts read the official Gazette PDFs.
pytest.importorskip("pymupdf", reason="PyMuPDF is needed to read the official PDFs "
                                      "(pip install pymupdf)")


def run_script(name: str, db_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a one-off script exactly the way Gautam would, but against a copy."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / name), "--db", str(db_path), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"{name} {' '.join(args)} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    return result


# The columns source_log has in the committed database today. Named explicitly
# rather than using SELECT *, because every entry point in this project calls
# init_schema(), which ADDS columns to an old database (additively, with
# defaults, touching no existing row). Comparing SELECT * would therefore report
# a schema upgrade as if it were a data change.
SOURCE_LOG_DATA_COLS = [
    "document_id", "source", "title", "url", "published_date", "fetched_date",
    "content_hash", "processing_status", "linked_change_ids",
]


def snapshot(db_path: Path) -> dict:
    """The database's DATA, for before/after comparison (see above re schema)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    data = {
        "provisions": [dict(r) for r in conn.execute(
            "SELECT provision_id, full_text, latest_change_id, last_updated_date "
            "FROM provisions ORDER BY provision_id")],
        "change_log": [dict(r) for r in conn.execute(
            "SELECT change_id, provision_id, change_origin, change_type, "
            "old_full_text, new_full_text, source_document "
            "FROM change_log ORDER BY change_id")],
        "source_log": [dict(r) for r in conn.execute(
            f"SELECT {','.join(SOURCE_LOG_DATA_COLS)} FROM source_log ORDER BY document_id")],
    }
    conn.close()
    return data


def watched_flags(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    flags = {r["document_id"]: r["watched"]
             for r in conn.execute("SELECT document_id, watched FROM source_log")}
    conn.close()
    return flags


@pytest.fixture
def db_copy(tmp_path):
    """A throwaway copy of the committed database."""
    if not LIVE_DB.exists():
        pytest.skip("db/dpdpa.db is not present")
    copy = tmp_path / "dpdpa_copy.db"
    shutil.copy2(LIVE_DB, copy)
    return copy


# --------------------------------------------------------------------------
# Every script: a dry run must change nothing at all
# --------------------------------------------------------------------------

@pytest.mark.parametrize("script", [
    "fix_corrigendum_schedules_2026-09-30.py",
    "restore_verbatim_wording_2026-09-30.py",
    "mark_unwatched_sources_2026-09-30.py",
])
def test_a_dry_run_changes_nothing(script, db_copy):
    """
    The single most important property of these scripts: running one without
    --apply must be as harmless as reading the file. A non-developer has to be
    able to rehearse it without risk.
    """
    before = snapshot(db_copy)
    result = run_script(script, db_copy)
    after = snapshot(db_copy)
    assert before == after, f"{script} changed the database during a dry run"
    # It must also SAY so, in words a non-developer will recognise.
    said_so = any(phrase in result.stdout.lower()
                  for phrase in ("dry run", "nothing to do", "nothing was written"))
    assert said_so, result.stdout


@pytest.mark.parametrize("script", [
    "fix_corrigendum_schedules_2026-09-30.py",
    "restore_verbatim_wording_2026-09-30.py",
    "mark_unwatched_sources_2026-09-30.py",
])
def test_a_dry_run_may_upgrade_the_schema_but_leaves_every_row_alone(script, db_copy):
    """
    Said out loud rather than left as a surprise: a dry run DOES write one thing
    to the database file — the additive schema migration every entry point in
    this project applies (init_schema). It adds columns that are missing, with
    their defaults. It never changes a value in an existing row, which is what
    the dry-run promise actually is.
    """
    conn = sqlite3.connect(db_copy)
    before_cols = {r[1] for r in conn.execute("PRAGMA table_info(source_log)")}
    conn.close()
    assert "watched" not in before_cols, (
        "the committed database is expected to predate the watched column"
    )

    run_script(script, db_copy)

    conn = sqlite3.connect(db_copy)
    after_cols = {r[1] for r in conn.execute("PRAGMA table_info(source_log)")}
    conn.close()
    assert before_cols <= after_cols, "a column was removed"
    assert "watched" in after_cols
    # Everything that was already there defaults to "still watched".
    assert set(watched_flags(db_copy).values()) == {1}


# --------------------------------------------------------------------------
# H-5: the corrigendum's Schedule items become government changes
# --------------------------------------------------------------------------

CORRIGENDUM_SCRIPT = "fix_corrigendum_schedules_2026-09-30.py"


def test_the_four_pairs_are_printed_for_approval(db_copy):
    """Gautam has to approve the wording, so the dry run must show it to him."""
    out = run_script(CORRIGENDUM_SCRIPT, db_copy).stdout
    assert "THE FOUR PHRASE PAIRS" in out
    for expected in ("everybody", "every body", "(18 or 2013)", "(18 of 2013)",
                     "(35 of 2019).", "(35 of 2019);"):
        assert expected in out, f"{expected!r} was not shown in the dry run"
    assert "NOT been approved" in out


def test_applying_adds_exactly_four_regulatory_rows_and_touches_nothing_else(db_copy):
    before = snapshot(db_copy)
    run_script(CORRIGENDUM_SCRIPT, db_copy, "--apply")
    after = snapshot(db_copy)

    # The legal text itself must NOT be rewritten: it is already correct.
    assert after["provisions"] == before["provisions"], (
        "provisions were modified; this script must only add change_log rows"
    )
    assert after["source_log"] == before["source_log"]

    before_ids = {r["change_id"] for r in before["change_log"]}
    new_rows = [r for r in after["change_log"] if r["change_id"] not in before_ids]
    assert len(new_rows) == 4, [r["change_id"] for r in new_rows]
    assert {r["provision_id"] for r in new_rows} == {"DPDPR-SCH1", "DPDPR-SCH4"}
    for row in new_rows:
        assert row["change_origin"] == "regulatory", row
        assert row["change_type"] == "Correction", row
        # Same source document as CHG-0086/87/88, so they group under one caption.
        assert "892(E)" in row["source_document"], row

    # The two whole-Schedule data corrections stay exactly as they were.
    for cid in ("CHG-0089", "CHG-0091"):
        old = next(r for r in before["change_log"] if r["change_id"] == cid)
        new = next(r for r in after["change_log"] if r["change_id"] == cid)
        assert old == new, f"{cid} was modified"


def test_the_corrigendum_pairs_are_unique_where_they_have_to_be(db_copy):
    """
    apply_change.py and the Word highlighter both need "appears exactly once".
    "(18 of 2013)" appears three times in the First Schedule, so a bare pair
    would highlight the wrong words.
    """
    run_script(CORRIGENDUM_SCRIPT, db_copy, "--apply")
    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT provision_id, new_full_text FROM change_log "
        "WHERE change_origin = 'regulatory' AND provision_id IN ('DPDPR-SCH1','DPDPR-SCH4')"
    ).fetchall()
    for row in rows:
        full_text = conn.execute(
            "SELECT full_text FROM provisions WHERE provision_id = ?", (row["provision_id"],)
        ).fetchone()["full_text"]
        assert full_text.count(row["new_full_text"]) == 1, (
            f"{row['provision_id']}: {row['new_full_text'][:60]!r} is not unique"
        )
    conn.close()


def test_the_corrigendum_script_is_safe_to_run_twice(db_copy):
    run_script(CORRIGENDUM_SCRIPT, db_copy, "--apply")
    once = snapshot(db_copy)
    second = run_script(CORRIGENDUM_SCRIPT, db_copy, "--apply")
    assert snapshot(db_copy) == once, "a second --apply changed the database again"
    assert "already recorded" in second.stdout


def test_the_new_rows_show_up_as_yellow_change_log_rows_and_schedule_highlights(db_copy):
    """
    The effect the audit asked for, checked on the real exporters: four more
    yellow rows in the Excel Change_Log, and the First and Fourth Schedules
    named as amended in the Word document.

    Note what is asserted about highlighting. Three of the four items highlight
    their changed words. The fourth — corrigendum item (v)(b), which relabels
    the Fourth Schedule Note's items (a)..(f) as (a)..(g) — changes a run of
    text that spans several paragraphs, and the renderer only ever highlights
    text it finds whole inside one paragraph. So that one is captioned rather
    than highlighted. That is the renderer's deliberate "caption it, but never
    highlight the wrong words" behaviour, and it is a warning on stderr, not a
    silent skip.
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "src"))
    import export_word as ew

    run_script(CORRIGENDUM_SCRIPT, db_copy, "--apply")
    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row

    for provision_id, expected in (("DPDPR-SCH1", 2), ("DPDPR-SCH4", 2)):
        amendments = ew.fetch_amendments(conn, provision_id)
        assert len(amendments) == expected, (
            f"{provision_id} should now report {expected} government changes"
        )

    # Excel: the same rows, and they are the ones the highlighter fills yellow.
    yellow = conn.execute(
        "SELECT change_id FROM change_log WHERE change_origin = 'regulatory' "
        "AND change_type != 'New Provision' ORDER BY change_id"
    ).fetchall()
    assert len(yellow) == 7, [r["change_id"] for r in yellow]  # 3 existing + 4 new
    conn.close()


# --------------------------------------------------------------------------
# H-7 + M-11: the verbatim wording
# --------------------------------------------------------------------------

RESTORE_SCRIPT = "restore_verbatim_wording_2026-09-30.py"


def test_the_two_seventh_schedule_strings_are_shown_side_by_side(db_copy):
    out = run_script(RESTORE_SCRIPT, db_copy).stdout
    assert "database holds" in out and "Gazette prints" in out
    assert "of a Data Principal for: (i) performance" in out
    assert "for the following purposes, namely:" in out


def test_all_fifteen_heading_dashes_are_shown_before_and_after(db_copy):
    out = run_script(RESTORE_SCRIPT, db_copy).stdout
    befores = [line for line in out.splitlines() if line.strip().startswith("before: ")]
    afters = [line for line in out.splitlines() if line.strip().startswith("after : ")]
    assert len(befores) == 15, befores
    assert len(afters) == 15, afters


def test_applying_restores_the_wording_as_our_own_correction(db_copy):
    before = snapshot(db_copy)
    run_script(RESTORE_SCRIPT, db_copy, "--apply")
    after = snapshot(db_copy)

    before_ids = {r["change_id"] for r in before["change_log"]}
    new_rows = [r for r in after["change_log"] if r["change_id"] not in before_ids]
    assert len(new_rows) == 3, [r["change_id"] for r in new_rows]
    assert {r["provision_id"] for r in new_rows} == {"DPDPR-SCH5", "DPDPR-SCH6", "DPDPR-SCH7"}
    for row in new_rows:
        # OUR mistake, not the government's — so it must never be highlighted
        # or reported as a change in the law.
        assert row["change_origin"] == "data_correction", row

    texts = {r["provision_id"]: r["full_text"] for r in after["provisions"]}
    assert "of a Data Principal for: (i) performance" not in texts["DPDPR-SCH7"]
    assert "for the following purposes, namely:" in texts["DPDPR-SCH7"]
    assert "1. **Salary.** — (1)" in texts["DPDPR-SCH5"]
    assert "1. **Classes of officials.** — (1)" in texts["DPDPR-SCH6"]

    assert after["source_log"] == before["source_log"]
    # Only those three provisions moved.
    changed = {r["provision_id"] for b, r in zip(before["provisions"], after["provisions"]) if b != r}
    assert changed == {"DPDPR-SCH5", "DPDPR-SCH6", "DPDPR-SCH7"}, changed


def test_a_data_correction_does_not_change_what_is_highlighted(db_copy):
    """
    The rule this whole session is built on: fixing our own typing must never
    alter what the documents show as a change in the law (audit H-6).
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "src"))
    import export_word as ew

    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    before = {r["provision_id"]: [dict(a) for a in ew.fetch_amendments(conn, r["provision_id"])]
              for r in conn.execute("SELECT provision_id FROM provisions")}
    conn.close()

    run_script(RESTORE_SCRIPT, db_copy, "--apply")

    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    after = {r["provision_id"]: [dict(a) for a in ew.fetch_amendments(conn, r["provision_id"])]
             for r in conn.execute("SELECT provision_id FROM provisions")}
    conn.close()
    assert before == after, "a data correction changed which amendments are rendered"


def test_the_restore_script_is_safe_to_run_twice(db_copy):
    run_script(RESTORE_SCRIPT, db_copy, "--apply")
    once = snapshot(db_copy)
    second = run_script(RESTORE_SCRIPT, db_copy, "--apply")
    assert snapshot(db_copy) == once, "a second --apply changed the database again"
    assert "Nothing to do" in second.stdout


def test_the_restored_text_matches_the_official_pdf_without_any_exception(db_copy):
    """
    The point of the whole exercise. After the fix, the project's own verbatim
    guard must accept these three provisions on their own merits — not because
    a reviewed exception excuses them.
    """
    pytest.importorskip("pdfplumber", reason="pdfplumber is needed by the verbatim guard")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "verbatim_guard", REPO_ROOT / "tests" / "test_legal_text_verbatim.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    run_script(RESTORE_SCRIPT, db_copy, "--apply")

    fixed = ("DPDPR-SCH5", "DPDPR-SCH6", "DPDPR-SCH7")
    for provision_id in fixed:
        guard._KNOWN_EXCEPTIONS.pop(provision_id, None)

    pdf_text = guard._normalize_rules(guard._extract_rules_english_text())
    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    for provision_id in fixed:
        full_text = conn.execute(
            "SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)
        ).fetchone()["full_text"]
        errors = guard.check_rules_provision(provision_id, full_text, pdf_text)
        assert errors == [], f"{provision_id} still differs from the Gazette:\n" + "\n".join(errors)
    conn.close()


# --------------------------------------------------------------------------
# M-5: the retired sources
# --------------------------------------------------------------------------

UNWATCH_SCRIPT = "mark_unwatched_sources_2026-09-30.py"
RETIRED = {"SRC-0003", "SRC-0004", "SRC-0005", "SRC-0006"}


def test_applying_retires_exactly_four_sources_and_deletes_nothing(db_copy):
    before = snapshot(db_copy)
    run_script(UNWATCH_SCRIPT, db_copy, "--apply")
    after = snapshot(db_copy)

    assert after["provisions"] == before["provisions"]
    assert after["change_log"] == before["change_log"]
    assert len(after["source_log"]) == len(before["source_log"]), "a row was deleted"

    flags = watched_flags(db_copy)
    assert {doc_id for doc_id, w in flags.items() if w == 0} == RETIRED, flags
    # Those rows carry linked_change_ids — the record of which change came from
    # where — so nothing about them may change except the watched flag itself.
    assert after["source_log"] == before["source_log"]


def test_the_unwatch_script_is_safe_to_run_twice(db_copy):
    run_script(UNWATCH_SCRIPT, db_copy, "--apply")
    once = snapshot(db_copy)
    second = run_script(UNWATCH_SCRIPT, db_copy, "--apply")
    assert snapshot(db_copy) == once
    assert "Nothing to do" in second.stdout


# --------------------------------------------------------------------------
# All three together, in the order Gautam will run them
# --------------------------------------------------------------------------

def test_the_three_scripts_run_together_in_order(db_copy):
    for script in (UNWATCH_SCRIPT, RESTORE_SCRIPT, CORRIGENDUM_SCRIPT):
        run_script(script, db_copy, "--apply")

    conn = sqlite3.connect(db_copy)
    conn.row_factory = sqlite3.Row
    # 3 data corrections + 4 government corrections = 7 new change_log rows.
    assert conn.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"] == 142 + 7
    # Only 3 sources still watched.
    assert conn.execute(
        "SELECT COUNT(*) c FROM source_log WHERE watched = 1").fetchone()["c"] == 3
    # Seven yellow (regulatory) rows for the Excel Change_Log sheet.
    assert conn.execute(
        "SELECT COUNT(*) c FROM change_log WHERE change_origin = 'regulatory' "
        "AND change_type != 'New Provision'").fetchone()["c"] == 7
    conn.close()
