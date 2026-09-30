"""
Phase 8: a permanent guard against the pipeline silently losing changes.
Covers: a download error surfacing into run_pipeline's errors/exit code, a
classification failure restoring the previous hash so the next run
retries, max_tokens raising ClassificationFailed, _validate rejecting
invented text, and apply_change replacing only the matching span (and
refusing on 0 or 2+ matches).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import apply_change as ac
import classify_change as cc
import fetch_sources as fs
import run_pipeline as rp
from classify_change import ClassificationFailed

from conftest import FakeFetchResult, seed_provision, seed_source_log


# --------------------------------------------------------------------------
# fetch_sources.py: download error handling
# --------------------------------------------------------------------------

def test_download_error_keeps_last_good_hash_and_reports_it(conn):
    seed_source_log(conn, document_id="SRC-0001", url=fs.SOURCES[0]["url"],
                     content_hash="GOODHASH123", processing_status="No Change Detected")
    errors = []
    with patch.object(fs, "_fetch_raw", side_effect=Exception("simulated network failure")):
        changed = fs.fetch_all(conn, fetch_errors=errors)

    assert changed == []
    assert len(errors) == len(fs.SOURCES)
    assert all("simulated network failure" in e for e in errors)
    row = conn.execute(
        "SELECT content_hash, processing_status FROM source_log WHERE url = ?", (fs.SOURCES[0]["url"],)
    ).fetchone()
    assert row["content_hash"] == "GOODHASH123", "must not blank the last good hash on failure"
    assert row["processing_status"] == "Error"
    # A failed fetch has no text, so it must not write a baseline either —
    # baking a failure in as "what the source said" would be worse than having
    # no baseline at all (audit C-3).
    assert conn.execute("SELECT COUNT(*) c FROM source_snapshot").fetchone()["c"] == 0


def test_every_source_log_row_gets_a_baseline_when_it_is_created(conn):
    """
    Audit finding C-3, the invariant. A "baseline" (source_snapshot row) is the
    text as we last saw it; classify_change.py diffs the next fetch against it.
    Before 30 Sep 2026 it was only created the first time a source CHANGED, so
    a source could sit in source_log for weeks with no baseline — and then have
    its first real change stored as the baseline and never reported. SRC-0001,
    the DPDP Rules PDF, was in exactly that state.
    """
    with patch.object(fs, "_fetch_raw", return_value=b"<html><body>hello</body></html>"), \
         patch.object(fs, "_extract_text", side_effect=lambda raw, kind: f"text for {kind}"):
        changed = fs.fetch_all(conn)

    assert len(changed) == len(fs.SOURCES), "every source is new, so every source changed"
    log_ids = {r["document_id"] for r in conn.execute("SELECT document_id FROM source_log")}
    snap_ids = {r["document_id"] for r in conn.execute("SELECT document_id FROM source_snapshot")}
    assert log_ids == snap_ids, (
        f"every watched source must have a baseline; missing: {sorted(log_ids - snap_ids)}"
    )
    row = conn.execute(
        "SELECT content_text FROM source_snapshot WHERE document_id = ?", (sorted(log_ids)[0],)
    ).fetchone()
    assert row["content_text"], "the baseline must hold the actual text, not an empty string"


def test_a_second_fetch_does_not_overwrite_the_baseline(conn):
    """
    The baseline must only move forward when classify_change.py says so (after
    a successful classification). fetch_all must never quietly advance it, or a
    change would be diffed away before anyone looked at it.
    """
    with patch.object(fs, "_fetch_raw", return_value=b"first"), \
         patch.object(fs, "_extract_text", side_effect=lambda raw, kind: "first text"):
        fs.fetch_all(conn)
    with patch.object(fs, "_fetch_raw", return_value=b"second"), \
         patch.object(fs, "_extract_text", side_effect=lambda raw, kind: "second text"):
        fs.fetch_all(conn)

    texts = {r["content_text"] for r in conn.execute("SELECT content_text FROM source_snapshot")}
    assert texts == {"first text"}, "fetch_all must not advance the baseline on a later fetch"


def test_download_error_without_fetch_errors_list_still_works(conn):
    """fetch_errors is optional — omitting it must not break anything."""
    with patch.object(fs, "_fetch_raw", side_effect=Exception("boom")):
        changed = fs.fetch_all(conn)
    assert changed == []


# --------------------------------------------------------------------------
# run_pipeline.py: classification failure restores the previous hash
# --------------------------------------------------------------------------

def test_classification_failure_restores_prior_hash_and_exits_1(conn, tmp_path):
    seed_source_log(conn, document_id="SRC-0001", url="http://x/doc.pdf",
                     content_hash="NEWHASH999", processing_status="New")
    conn.close()

    db_path = tmp_path / "test.db"
    fr = FakeFetchResult(document_id="SRC-0001", url="http://x/doc.pdf",
                          content_hash="NEWHASH999", prior_hash="OLDHASH111")

    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[fr]), \
         patch.object(rp, "classify", side_effect=ClassificationFailed("simulated max_tokens")), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()

    assert rc == 1
    conn2 = db_module.get_connection(db_path)
    row = conn2.execute("SELECT content_hash FROM source_log WHERE document_id = ?", ("SRC-0001",)).fetchone()
    assert row["content_hash"] == "OLDHASH111", "prior hash must be restored so the next run retries"
    conn2.close()

    errors_arg = mock_notify.call_args[0][1]
    assert any("simulated max_tokens" in e for e in errors_arg)


def test_first_sighting_stores_a_baseline_makes_no_ai_call_and_says_so(conn, tmp_path):
    """
    Case (i) of audit finding C-3: genuinely the FIRST time this source has
    been fetched (no prior fingerprint). Storing today's text as the baseline
    is right — there is nothing to compare against — but it must be REPORTED,
    or a day on which the tool learnt something for the first time reads
    exactly like a quiet day. Exit 0, no Claude call, and a note in the email.
    """
    seed_source_log(conn, document_id="SRC-0001", url="http://x/2025/11/y.pdf",
                     content_hash="h1", processing_status="New")
    conn.close()

    db_path = tmp_path / "test.db"
    fr = FakeFetchResult(source="MeitY", document_id="SRC-0001", url="http://x/2025/11/y.pdf",
                          content_text="Rule 1. Short title.", content_hash="h1", prior_hash=None)

    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[fr]), \
         patch.object(cc, "_call_claude") as mock_claude, \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()

    assert rc == 0
    mock_claude.assert_not_called()
    applied, errors = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
    assert applied == []
    assert errors == []
    notes = mock_notify.call_args.kwargs["baseline_notes"]
    assert any("first check of MeitY" in n and "SRC-0001" in n for n in notes), notes

    # And the email actually prints it.
    from notify import _build_body
    _subject, body = _build_body([], [], 1, 1, baseline_notes=notes)
    assert "first check of MeitY" in body
    assert "Baselines captured" in body


def test_a_source_with_history_but_no_baseline_is_a_loud_error(conn, tmp_path):
    """
    Case (ii) of audit finding C-3, and the one that mattered: the source has
    been fetched before (source_log holds a prior fingerprint) but has no
    baseline text. Storing today's text as "the baseline" would swallow the
    very change that triggered the run — which is exactly what would have
    happened to the next amendment of the DPDP Rules.

    Required behaviour: raise, report, and put the old fingerprint back so the
    source is retried tomorrow instead of written off.
    """
    seed_source_log(conn, document_id="SRC-0001", url="http://x/2025/11/y.pdf",
                     content_hash="NEWHASH", processing_status="New")
    conn.close()

    db_path = tmp_path / "test.db"
    fr = FakeFetchResult(source="MeitY", document_id="SRC-0001", url="http://x/2025/11/y.pdf",
                          content_text="Rule 1. Short title. Twelve months instead of eighteen.",
                          content_hash="NEWHASH", prior_hash="OLDHASH")

    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[fr]), \
         patch.object(cc, "_call_claude") as mock_claude, \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()

    assert rc == 1, "this must not be reported as a clean run"
    mock_claude.assert_not_called()
    errors = mock_notify.call_args[0][1]
    assert any("no baseline for SRC-0001" in e for e in errors), errors
    assert any("backfill_source_snapshots" in e for e in errors), \
        "the error must say what to run to fix it"

    conn2 = db_module.get_connection(db_path)
    assert conn2.execute(
        "SELECT content_hash FROM source_log WHERE document_id = 'SRC-0001'"
    ).fetchone()["content_hash"] == "OLDHASH", "the fingerprint must roll back so tomorrow retries"
    assert conn2.execute("SELECT COUNT(*) c FROM source_snapshot").fetchone()["c"] == 0, \
        "today's text must NOT have been stored as the baseline"
    conn2.close()


# --------------------------------------------------------------------------
# classify_change.py: max_tokens, and _validate rejecting invented text
# --------------------------------------------------------------------------

def test_max_tokens_raises_classification_failed():
    class FakeResp:
        stop_reason = "max_tokens"
        content = []

    with patch.object(cc, "ANTHROPIC_API_KEY", "fake-key"), \
         patch("anthropic.Anthropic") as mock_client_cls:
        mock_client_cls.return_value.messages.create.return_value = FakeResp()
        with pytest.raises(ClassificationFailed, match="max_tokens"):
            cc._call_claude("irrelevant prompt")


def test_validate_rejects_invented_old_full_text():
    provisions = [{"provision_id": "DPDPR-R23", "reference": "Rule 23(1)", "full_text": "given in such order."}]
    fr = FakeFetchResult(content_text="given in such order. some other text.")
    bad = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "this text was never in the provision",
        "new_full_text": "given in such order.", "confidence_score": 0.9,
    }
    with pytest.raises(ValueError, match="invented text"):
        cc._validate({"changes": [bad]}, provisions, fr)


def test_validate_rejects_invented_new_full_text():
    provisions = [{"provision_id": "DPDPR-R23", "reference": "Rule 23(1)", "full_text": "given in such order."}]
    fr = FakeFetchResult(content_text="given in such order. some other text.")
    bad = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "given in such order.",
        "new_full_text": "this text was never in the fetched content", "confidence_score": 0.9,
    }
    with pytest.raises(ValueError, match="invented text"):
        cc._validate({"changes": [bad]}, provisions, fr)


def test_validate_accepts_a_genuine_matching_change():
    provisions = [{"provision_id": "DPDPR-R23", "reference": "Rule 23(1)", "full_text": "given in such order."}]
    fr = FakeFetchResult(content_text="given in such order. some other text.")
    good = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "given in such order.",
        "new_full_text": "given in such order.", "confidence_score": 0.9,
    }
    result = cc._validate({"changes": [good]}, provisions, fr)
    assert result == [good]


# --------------------------------------------------------------------------
# apply_change.py: span replacement, refusal on 0/2+ matches
# --------------------------------------------------------------------------

# The URL matters now: apply() refuses a change from a source that is not
# allowed to make it (audit C-4). The official MeitY Rules PDF is the only
# source allowed to change a DPDPR-* row, so that is what these tests use.
RULES_PDF_URL = fs.SOURCES[1]["url"]
PIB_URL = fs.SOURCES[0]["url"]
EGAZETTE_HOME_URL = fs.RETIRED_SOURCES[0]["url"]


def _fr(document_id="SRC-0099", url=None, source="MeitY"):
    from types import SimpleNamespace
    return SimpleNamespace(document_id=document_id, title="test",
                            url=url or RULES_PDF_URL, source=source)


def test_apply_change_replaces_only_the_matching_span(conn):
    seed_provision(conn, full_text="given in such.")
    seed_source_log(conn)
    change = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "given in such.", "new_full_text": "given in such order.",
        "confidence_score": 0.9,
    }
    cid = ac.apply(change, _fr(), conn, "test-model")
    row = conn.execute("SELECT full_text, current_summary, latest_change_id FROM provisions WHERE provision_id=?",
                        ("DPDPR-R23",)).fetchone()
    assert row["full_text"] == "given in such order."
    assert row["current_summary"] == "Appeals process summary.", "current_summary must never be overwritten"
    assert row["latest_change_id"] == cid


def test_apply_change_refuses_when_span_matches_twice(conn):
    seed_provision(conn, full_text="given in such. given in such.")
    seed_source_log(conn)
    change = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "given in such.", "new_full_text": "given in such order.",
        "confidence_score": 0.9,
    }
    with pytest.raises(ValueError, match="matches the current full_text 2 time"):
        ac.apply(change, _fr(), conn, "test-model")

    row = conn.execute("SELECT full_text, latest_change_id FROM provisions WHERE provision_id=?",
                        ("DPDPR-R23",)).fetchone()
    assert row["full_text"] == "given in such. given in such."
    assert row["latest_change_id"] is None
    assert conn.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"] == 0, \
        "a refused apply must write nothing to change_log either"


def test_apply_change_refuses_when_span_matches_zero_times(conn):
    seed_provision(conn, full_text="completely different text.")
    seed_source_log(conn)
    change = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "given in such.", "new_full_text": "given in such order.",
        "confidence_score": 0.9,
    }
    with pytest.raises(ValueError, match="matches the current full_text 0 time"):
        ac.apply(change, _fr(), conn, "test-model")
    assert conn.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"] == 0


def test_apply_change_new_provision_gets_pending_review_and_null_effective_date(conn):
    seed_source_log(conn)
    change = {
        "provision_id": "DPDPR-R24", "change_type": "New Provision",
        "old_value_summary": None, "new_value_summary": "a brand new rule",
        "old_full_text": None, "new_full_text": "The text of new Rule 24.",
        "confidence_score": 0.9,
    }
    ac.apply(change, _fr(), conn, "test-model")
    row = conn.execute(
        "SELECT reference, instrument_type, review_status, effective_date, notes FROM provisions WHERE provision_id=?",
        ("DPDPR-R24",),
    ).fetchone()
    assert row["reference"] == "Rule 24"
    assert row["instrument_type"] == "Rule"
    assert row["review_status"] == "Pending Review"
    assert row["effective_date"] is None
    assert "commencement to be confirmed" in row["notes"].lower()
