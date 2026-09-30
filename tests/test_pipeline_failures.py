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

# The URL matters now: apply() refuses a change from a source that is not
# allowed to make it (audit C-4). The official MeitY Rules PDF is the only
# source allowed to change a DPDPR-* row, so that is what these tests use.
RULES_PDF_URL = fs.SOURCES[1]["url"]
PIB_URL = fs.SOURCES[0]["url"]
EGAZETTE_HOME_URL = fs.RETIRED_SOURCES[0]["url"]


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
# run_pipeline.py: an apply() failure rolls the whole source back (audit H-2)
# --------------------------------------------------------------------------

# Rule 1's real text, which contains the phrase "of publication in the Official
# Gazette" TWICE — once in sub-rule (3) and once in (4). apply_change refuses to
# touch a span that appears more than once, which is the deliberate safety
# refusal that used to lose the change forever.
R1_TEXT = (
    "(3) Rules 2, 4, 17 to 21 shall come into force on the date of publication in the "
    "Official Gazette.\n\n"
    "(4) Rules 3, 5 to 16, 22 and 23 shall come into force eighteen months after the "
    "date of publication in the Official Gazette."
)
AMBIGUOUS_CHANGE = {
    "provision_id": "DPDPR-R1", "change_type": "Amendment",
    "old_value_summary": "a", "new_value_summary": "b",
    "old_full_text": "of publication in the Official Gazette",
    "new_full_text": "of publication of this Gazette",
    "confidence_score": 0.9,
}
OLD_BASELINE = "Rule 1.\n" + R1_TEXT
NEW_FETCH = OLD_BASELINE + "\nof publication of this Gazette"


def _seed_rule_1(conn, document_id="SRC-0001"):
    seed_provision(conn, provision_id="DPDPR-R1", reference="Rule 1",
                    full_text=R1_TEXT, full_text_anchor="DPDPR_R1")
    seed_source_log(conn, document_id=document_id, url=RULES_PDF_URL,
                     content_hash="NEWHASH", processing_status="New")
    conn.execute(
        "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) "
        "VALUES (?, 'OLDHASH', ?, '2026-09-29')",
        (document_id, OLD_BASELINE),
    )
    conn.commit()


def _run_with_reply(db_path, fr, reply):
    import db as db_module
    with patch.object(rp, "get_connection", lambda: db_module.get_connection(db_path)), \
         patch.object(rp, "fetch_all", return_value=[fr]), \
         patch.object(cc, "_call_claude", return_value=reply), \
         patch.object(rp, "discover_all", return_value=([], [])), \
         patch.object(rp, "send_summary") as mock_notify:
        rc = rp.main()
    return rc, mock_notify


def test_a_refused_apply_rolls_back_the_fingerprint_and_the_baseline(conn, tmp_path):
    """
    Audit finding H-2. apply_change refuses to replace a span that appears more
    than once — a deliberate safety rule. Before this fix, the fingerprint and
    the baseline had already moved on by then, so the next run saw no change and
    the detected amendment was gone for good. You got one error email, on one
    day, and that was your only chance to notice.
    """
    _seed_rule_1(conn)
    conn.close()

    db_path = tmp_path / "test.db"
    fr = FakeFetchResult(source="MeitY", document_id="SRC-0001", url=RULES_PDF_URL,
                          content_text=NEW_FETCH, content_hash="NEWHASH", prior_hash="OLDHASH")
    rc, mock_notify = _run_with_reply(db_path, fr, {"changes": [AMBIGUOUS_CHANGE]})

    assert rc == 1
    errors = mock_notify.call_args[0][1]
    assert any("matches the current full_text 2 time" in e for e in errors), errors

    import db as db_module
    conn2 = db_module.get_connection(db_path)
    assert conn2.execute(
        "SELECT content_hash FROM source_log WHERE document_id = 'SRC-0001'"
    ).fetchone()["content_hash"] == "OLDHASH", \
        "the fingerprint must roll back, or tomorrow's run sees no change"
    snap = conn2.execute(
        "SELECT content_hash, content_text FROM source_snapshot WHERE document_id = 'SRC-0001'"
    ).fetchone()
    assert snap["content_hash"] == "OLDHASH"
    assert snap["content_text"] == OLD_BASELINE, \
        "the baseline must roll back, or tomorrow's diff is empty"
    assert conn2.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"] == 0
    assert conn2.execute(
        "SELECT processing_status FROM source_log WHERE document_id = 'SRC-0001'"
    ).fetchone()["processing_status"] == "Error"
    conn2.close()


def test_the_retry_the_next_day_sees_the_change_again(conn, tmp_path):
    """The point of the rollback: run the same day twice and the second run must
    still see something to look at, not an empty diff."""
    _seed_rule_1(conn)
    conn.close()

    db_path = tmp_path / "test.db"
    fr = FakeFetchResult(source="MeitY", document_id="SRC-0001", url=RULES_PDF_URL,
                          content_text=NEW_FETCH, content_hash="NEWHASH", prior_hash="OLDHASH")
    _run_with_reply(db_path, fr, {"changes": [AMBIGUOUS_CHANGE]})

    # Second run, same fetch (the fingerprint rolled back, so fetch_all would
    # report this source as changed again).
    rc, mock_notify = _run_with_reply(db_path, fr, {"changes": [AMBIGUOUS_CHANGE]})
    assert rc == 1, "the second run must still notice the change, not report a quiet day"
    errors = mock_notify.call_args[0][1]
    assert any("matches the current full_text 2 time" in e for e in errors), errors


def test_a_source_with_no_baseline_at_all_is_not_left_with_one(conn, tmp_path):
    """
    Edge case of the rollback: if there was no baseline before the run, there
    must be none after a failed apply either. Leaving today's text behind would
    make tomorrow's diff empty — the very failure this guards against.
    """
    seed_provision(conn, provision_id="DPDPR-R1", reference="Rule 1",
                    full_text=R1_TEXT, full_text_anchor="DPDPR_R1")
    seed_source_log(conn, document_id="SRC-0001", url=RULES_PDF_URL,
                     content_hash="NEWHASH", processing_status="New")
    conn.close()

    db_path = tmp_path / "test.db"
    # prior_hash=None means "first sighting", so classify stores a baseline and
    # returns nothing — no apply, nothing to roll back. Force the apply path by
    # giving it history AND a hand-made baseline is what the test above does;
    # here the baseline is genuinely absent but history exists, which now raises
    # ClassificationFailed. Assert the fingerprint rolls back and no baseline is
    # left behind.
    fr = FakeFetchResult(source="MeitY", document_id="SRC-0001", url=RULES_PDF_URL,
                          content_text=NEW_FETCH, content_hash="NEWHASH", prior_hash="OLDHASH")
    rc, _mock = _run_with_reply(db_path, fr, {"changes": []})
    assert rc == 1

    import db as db_module
    conn2 = db_module.get_connection(db_path)
    assert conn2.execute("SELECT COUNT(*) c FROM source_snapshot").fetchone()["c"] == 0
    assert conn2.execute(
        "SELECT content_hash FROM source_log WHERE document_id = 'SRC-0001'"
    ).fetchone()["content_hash"] == "OLDHASH"
    conn2.close()


def test_reprocessing_after_a_partial_failure_does_not_duplicate(conn, tmp_path):
    """
    The deliberate choice recorded in run_pipeline: when one change out of
    several fails, the ones that applied are KEPT and only the fingerprint and
    baseline roll back. That is only safe if re-processing cannot apply the same
    change twice — and it cannot, because apply_change refuses unless
    old_full_text appears in the current text exactly once. Once applied, it
    appears zero times.
    """
    seed_provision(conn, provision_id="DPDPR-R23", reference="Rule 23(1)",
                    full_text="given in such.", full_text_anchor="DPDPR_R23")
    seed_provision(conn, provision_id="DPDPR-R1", reference="Rule 1",
                    full_text=R1_TEXT, full_text_anchor="DPDPR_R1", sort_order=2)
    seed_source_log(conn, document_id="SRC-0001", url=RULES_PDF_URL,
                     content_hash="NEWHASH", processing_status="New")
    good = {
        "provision_id": "DPDPR-R23", "change_type": "Correction",
        "old_value_summary": "a", "new_value_summary": "b",
        "old_full_text": "given in such.", "new_full_text": "given in such order.",
        "confidence_score": 0.9,
    }
    text = "given in such order.\n" + NEW_FETCH
    conn.execute(
        "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) "
        "VALUES ('SRC-0001', 'OLDHASH', ?, '2026-09-29')", ("given in such.\n" + OLD_BASELINE,))
    conn.commit()
    conn.close()

    db_path = tmp_path / "test.db"
    fr = FakeFetchResult(source="MeitY", document_id="SRC-0001", url=RULES_PDF_URL,
                          content_text=text, content_hash="NEWHASH", prior_hash="OLDHASH")
    reply = {"changes": [good, AMBIGUOUS_CHANGE]}

    rc1, _ = _run_with_reply(db_path, fr, reply)
    assert rc1 == 1

    import db as db_module
    conn2 = db_module.get_connection(db_path)
    after_first = conn2.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"]
    assert after_first == 1, "the change that worked is kept"
    conn2.close()

    rc2, _ = _run_with_reply(db_path, fr, reply)
    assert rc2 == 1

    conn3 = db_module.get_connection(db_path)
    assert conn3.execute("SELECT COUNT(*) c FROM change_log").fetchone()["c"] == 1, \
        "re-processing must not apply the same change a second time"
    assert conn3.execute(
        "SELECT full_text FROM provisions WHERE provision_id = 'DPDPR-R23'"
    ).fetchone()["full_text"] == "given in such order."
    conn3.close()


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
