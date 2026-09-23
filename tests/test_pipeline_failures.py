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
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()

    assert rc == 1
    conn2 = db_module.get_connection(db_path)
    row = conn2.execute("SELECT content_hash FROM source_log WHERE document_id = ?", ("SRC-0001",)).fetchone()
    assert row["content_hash"] == "OLDHASH111", "prior hash must be restored so the next run retries"
    conn2.close()

    errors_arg = mock_notify.call_args[0][1]
    assert any("simulated max_tokens" in e for e in errors_arg)


def test_baseline_capture_is_not_an_error_and_makes_no_ai_call(conn, tmp_path):
    """First-ever check of a source (no snapshot yet): store one, report
    'baseline captured', exit 0, and never touch the Claude API."""
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
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()

    assert rc == 0
    mock_claude.assert_not_called()
    applied, errors = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
    assert applied == []
    assert errors == []


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

def _fr(document_id="SRC-0099"):
    from types import SimpleNamespace
    return SimpleNamespace(document_id=document_id, title="test", url="http://x")


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
