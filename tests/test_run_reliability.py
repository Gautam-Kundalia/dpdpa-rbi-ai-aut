"""
Audit findings M-2, M-13 and M-14, plus one guard of its own.

M-2  A reply the validator rejects is a decision, not an accident — asking the
     same question twice more just costs three times as much.
M-13 The run must write to the database it was told to use, never quietly to
     the real one.
M-14 The daily job commits the database and the documents back to GitHub with
     `if: always()`. A run killed half way through therefore committed a
     database that no longer matched the documents beside it. A "this run
     finished" marker file makes that answerable.

Everything here uses a mock AI. No network, no API calls, no cost.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import anthropic
import classify_change as cc
import fetch_sources as fs
import run_pipeline as rp

from conftest import FakeFetchResult, seed_provision, seed_source_log

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_PDF_URL = fs.SOURCES[1]["url"]

OLD_TEXT = "given in such."
NEW_TEXT = "given in such order."
BASELINE = "Rule 23.\n" + OLD_TEXT
FETCHED = "Rule 23.\n" + NEW_TEXT
GOOD_CHANGE = {
    "provision_id": "DPDPR-R23", "change_type": "Correction",
    "old_value_summary": "a", "new_value_summary": "b",
    "old_full_text": OLD_TEXT, "new_full_text": NEW_TEXT,
    "confidence_score": 0.9,
}


def _seed(conn, document_id="SRC-0001"):
    seed_provision(conn, provision_id="DPDPR-R23", reference="Rule 23(1)",
                    full_text=OLD_TEXT, full_text_anchor="DPDPR_R23")
    seed_source_log(conn, document_id=document_id, url=RULES_PDF_URL,
                     content_hash="NEWHASH", processing_status="New")
    conn.execute(
        "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) "
        "VALUES (?, 'OLDHASH', ?, '2026-09-29')", (document_id, BASELINE))
    conn.commit()


def _fetch_result():
    return FakeFetchResult(source="MeitY", document_id="SRC-0001", url=RULES_PDF_URL,
                            content_text=FETCHED, content_hash="NEWHASH", prior_hash="OLDHASH")


def _run(db_path, reply=None, claude_side_effect=None):
    import db as db_module
    kwargs = {"return_value": reply} if claude_side_effect is None else {"side_effect": claude_side_effect}
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[_fetch_result()]), \
         patch.object(cc, "_call_claude", **kwargs) as mock_claude, \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()
    return rc, mock_claude, mock_notify


# --------------------------------------------------------------------------
# M-2: retry transport failures, never a decision
# --------------------------------------------------------------------------

def test_a_rejected_reply_costs_exactly_one_ai_call(conn):
    """
    The model answers, the answer fails the verbatim check. Asking again will
    get the same answer, so it must not be asked again. Before 30 Sep 2026 this
    cost three calls.
    """
    _seed(conn)
    invented = dict(GOOD_CHANGE, old_full_text="text that was never in the provision")
    with patch.object(cc, "_call_claude", return_value={"changes": [invented]}) as mock_claude:
        with pytest.raises(cc.ClassificationFailed, match="invented text"):
            cc.classify(_fetch_result(), conn)
    assert mock_claude.call_count == 1, (
        f"a deterministic rejection was retried {mock_claude.call_count} times — "
        f"that is the same wrong answer at three times the price"
    )


def test_a_reply_that_is_too_long_is_not_retried_either(conn):
    """max_tokens is a real failure, not a transient one — the code comment in
    _call_claude has said so all along, but the retry loop retried it anyway."""
    _seed(conn)
    with patch.object(cc, "_call_claude",
                      side_effect=cc.ClassificationFailed("Claude hit max_tokens")) as mock_claude:
        with pytest.raises(cc.ClassificationFailed):
            cc.classify(_fetch_result(), conn)
    assert mock_claude.call_count == 1


def test_a_connection_failure_IS_retried(conn):
    """The other half of M-2: a genuine transport failure must still be retried,
    or one blip loses the day."""
    _seed(conn)
    boom = anthropic.APIConnectionError(request=None)
    with patch.object(cc, "_call_claude", side_effect=boom) as mock_claude:
        with pytest.raises(cc.ClassificationFailed):
            cc.classify(_fetch_result(), conn)
    assert mock_claude.call_count == cc.MAX_CLASSIFY_ATTEMPTS


def test_a_transport_failure_that_clears_on_the_second_try_succeeds(conn):
    _seed(conn)
    boom = anthropic.APIConnectionError(request=None)
    with patch.object(cc, "_call_claude",
                      side_effect=[boom, {"changes": [GOOD_CHANGE]}]) as mock_claude:
        result = cc.classify(_fetch_result(), conn)
    assert mock_claude.call_count == 2
    assert len(result) == 1


def test_every_retryable_error_is_a_real_anthropic_class():
    """Guards against a typo silently emptying the retry list, which would turn
    every transient blip into a lost day."""
    assert cc.RETRYABLE_API_ERRORS, "the retryable-error list is empty"
    for cls in cc.RETRYABLE_API_ERRORS:
        assert issubclass(cls, BaseException)
    assert anthropic.APIConnectionError in cc.RETRYABLE_API_ERRORS
    assert anthropic.RateLimitError in cc.RETRYABLE_API_ERRORS


# --------------------------------------------------------------------------
# M-13: the run writes to the database it was given
# --------------------------------------------------------------------------

def test_the_run_never_touches_the_real_database(conn, tmp_path, marker):
    """
    run_pipeline used to open a SECOND connection on the hard-coded default
    database path to mark discovered documents as alerted, so a test run still
    wrote to db/dpdpa.db. Proved here by watching get_connection: every
    connection this run opens must be the temp one.
    """
    _seed(conn)
    conn.close()
    db_path = tmp_path / "test.db"

    import db as db_module
    opened: list[str] = []

    def tracking_get_connection(path=db_module.DB_PATH):
        opened.append(str(path))
        return db_module.get_connection(db_path)

    new_doc = {
        "url": "https://egazette.gov.in/WriteReadData/2026/999999.pdf",
        "title": "Some new gazette document", "discovery_source": "egazette-meity",
        "published_date": "2026-09-30", "matched_keywords": ["DPDP"],
        "text_excerpt": "x", "unreadable": False,
    }
    # Record which file mark_alerted was pointed at, while its connection is
    # still open (run_pipeline closes it before returning).
    marked_database: list[str] = []

    def record(connection, urls):
        marked_database.append(
            [row[2] for row in connection.execute("PRAGMA database_list").fetchall()
             if row[1] == "main"][0]
        )

    with patch.object(rp, "get_connection", tracking_get_connection), \
         patch.object(rp, "fetch_all", return_value=[]), \
         patch.object(rp, "discover_all", return_value=([new_doc], [])), \
         patch.object(rp, "mark_alerted", side_effect=record), \
         patch.object(rp, "send_summary"):
        rp.main()

    assert len(opened) == 1, (
        f"run_pipeline opened {len(opened)} connections; it must open exactly one so it "
        f"can be pointed at a test database: {opened}"
    )
    assert marked_database, "mark_alerted was never called"
    assert Path(marked_database[0]).resolve() == db_path.resolve(), (
        "mark_alerted wrote to a different database from the one the run was given"
    )


# --------------------------------------------------------------------------
# M-14: the "this run finished" marker
# --------------------------------------------------------------------------

@pytest.fixture
def marker(tmp_path, monkeypatch):
    path = tmp_path / "var" / "pipeline_complete"
    monkeypatch.setattr(rp, "COMPLETE_MARKER", path)
    return path


def test_the_marker_is_written_on_an_ordinary_quiet_run(tmp_path, marker):
    db_path = tmp_path / "test.db"
    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[]), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary"):
        rc = rp.main()
    assert rc == 0
    assert marker.exists(), "a completed run must be safe to commit"
    assert "documents regenerated: none needed" in marker.read_text(encoding="utf-8")


def _one_source_down(conn, fetch_errors=None, repeated_errors=None):
    """Stands in for fetch_all: one source could not be reached, nothing changed."""
    if fetch_errors is not None:
        fetch_errors.append("fetch failed for MeitY: simulated")
    return []


def test_the_marker_is_still_written_when_a_source_was_unreachable(tmp_path, marker):
    """A harmless error — one source down — must not stop the day's results being
    committed, or a single flaky source would freeze the database forever."""
    db_path = tmp_path / "test.db"
    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", side_effect=_one_source_down), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary"):
        rc = rp.main()
    assert rc == 1, "the error must still show up"
    assert marker.exists(), "but the run did reach the end, so its results are committable"


def test_a_previous_runs_marker_is_deleted_at_the_start(tmp_path, marker):
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("stale marker from yesterday", encoding="utf-8")
    db_path = tmp_path / "test.db"
    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[]), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary"):
        rp.main()
    assert "stale marker from yesterday" not in marker.read_text(encoding="utf-8")


def test_a_run_that_dies_part_way_through_leaves_no_marker(tmp_path, marker):
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("stale marker from yesterday", encoding="utf-8")
    db_path = tmp_path / "test.db"
    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", side_effect=KeyboardInterrupt("killed mid-run")):
        with pytest.raises(KeyboardInterrupt):
            rp.main()
    assert not marker.exists(), (
        "a killed run must leave no marker, so the workflow commits nothing and "
        "tomorrow redoes the work"
    )


def test_no_marker_when_a_document_export_fails(tmp_path, marker, monkeypatch):
    """
    The case M-14 is really about: a change was applied, so the Word and Excel
    files must be rebuilt — and one of them failed. The database and the
    documents may now disagree, so nothing may be committed.
    """
    db_path = tmp_path / "test.db"
    import db as db_module
    conn = db_module.get_connection(db_path)
    db_module.init_schema(conn)
    _seed(conn)
    conn.close()

    # Pretend this IS the real database, so the export step runs at all.
    monkeypatch.setattr(rp, "DB_PATH", db_path.resolve())

    class FailedRun:
        returncode = 3

    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[_fetch_result()]), \
         patch.object(cc, "_call_claude", return_value={"changes": [GOOD_CHANGE]}), \
         patch.object(rp.subprocess, "run", return_value=FailedRun()), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()

    assert rc == 1
    errors = mock_notify.call_args[0][1]
    assert any("exited with code 3" in e for e in errors), errors
    assert not marker.exists(), (
        "the documents could not be rebuilt, so the database must not be committed "
        "on its own"
    )


def test_the_marker_is_written_when_the_exports_succeed(tmp_path, marker, monkeypatch):
    db_path = tmp_path / "test.db"
    import db as db_module
    conn = db_module.get_connection(db_path)
    db_module.init_schema(conn)
    _seed(conn)
    conn.close()
    monkeypatch.setattr(rp, "DB_PATH", db_path.resolve())

    class OkRun:
        returncode = 0

    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[_fetch_result()]), \
         patch.object(cc, "_call_claude", return_value={"changes": [GOOD_CHANGE]}), \
         patch.object(rp.subprocess, "run", return_value=OkRun()), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary"):
        rc = rp.main()

    assert rc == 0
    assert marker.exists()
    assert "export_word.py" in marker.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# A guard of its own: the test suite must not rewrite the tracked documents
# --------------------------------------------------------------------------

def test_the_pipeline_refuses_to_rebuild_the_tracked_documents_from_a_test_database(tmp_path, marker):
    """
    export_word.py and export_excel.py always read db/dpdpa.db and always write
    docs/*.docx and data/*.xlsx. A test run that applied a change therefore used
    to overwrite the real, committed documents with unrelated data — which is
    exactly the kind of thing the project's rules forbid. run_pipeline now only
    regenerates them when it is genuinely on the tracked database.
    """
    db_path = tmp_path / "test.db"
    import db as db_module
    conn = db_module.get_connection(db_path)
    db_module.init_schema(conn)
    _seed(conn)
    conn.close()

    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[_fetch_result()]), \
         patch.object(cc, "_call_claude", return_value={"changes": [GOOD_CHANGE]}), \
         patch.object(rp.subprocess, "run") as mock_subprocess, \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary"):
        rc = rp.main()

    assert rc == 0
    mock_subprocess.assert_not_called(), "no export may run against a test database"
