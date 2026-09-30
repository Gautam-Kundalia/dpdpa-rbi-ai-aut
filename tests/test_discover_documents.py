"""
Tests for the alert-only document discovery layer (src/discover_documents.py).
Real network calls (Playwright, requests) are never made here — every source
is a fake fetch function, and PDF downloads are mocked with either inline
bytes or the one real, committed fixture PDF (the December 2025 corrigendum
already used elsewhere in this project as the known-answer test case). No
test here calls the Anthropic API.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import discover_documents as dd

REPO_ROOT = Path(__file__).resolve().parent.parent
CORRIGENDUM_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "GSR892E_Rules_corrigendum_official.pdf"


def _item(url: str, title: str, published_date: str = "2026-01-01") -> dict:
    return {"url": url, "title": title, "published_date": published_date}


def _source(name: str, fetch, all_items_relevant: bool = False) -> dict:
    return {"name": name, "fetch": fetch, "all_items_relevant": all_items_relevant}


def _static_fetch(name: str, items: list[dict], warnings: list[str] | None = None):
    # discover_all passes conn= now, so a source can look up when it last ran
    # and widen its own search window after an outage (audit M-12). **kwargs
    # keeps these stand-ins indifferent to that.
    return lambda **kwargs: {
        "items": items,
        "bucket_counts": {name: len(items)},
        "warnings": warnings or [],
    }


# --------------------------------------------------------------------------
# 1-2: baseline behaviour
# --------------------------------------------------------------------------

def test_baseline_stores_everything_alerts_nothing_and_notes_once(conn):
    items = [_item("https://x.test/a.pdf", "Doc A"), _item("https://x.test/b.html", "Doc B")]
    src = _source("src1", _static_fetch("src1", items))

    with patch.object(dd, "DISCOVERY_SOURCES", [src]):
        new_documents, baseline_notes = dd.discover_all(conn, [])

    assert new_documents == []
    assert baseline_notes == ["baseline captured for src1: 2 document(s)"]
    rows = conn.execute("SELECT url, is_baseline, alerted FROM discovered_documents ORDER BY url").fetchall()
    assert len(rows) == 2
    assert all(r["is_baseline"] == 1 and r["alerted"] == 1 for r in rows)


def test_second_run_with_same_list_produces_no_alerts(conn):
    items = [_item("https://x.test/a.pdf", "Doc A")]
    src = _source("src1", _static_fetch("src1", items))

    with patch.object(dd, "DISCOVERY_SOURCES", [src]):
        dd.discover_all(conn, [])  # baseline
        new_documents, baseline_notes = dd.discover_all(conn, [])  # identical list again

    assert new_documents == []
    assert baseline_notes == []


# --------------------------------------------------------------------------
# 3: the corrigendum replay — the whole point of this task
# --------------------------------------------------------------------------

def test_corrigendum_replay_is_found_via_pdf_text_not_title_or_url(conn):
    # A hashed-filename-style URL and a neutral title, deliberately containing
    # none of the KEYWORDS substrings, to prove this can only be caught by
    # reading the PDF's own text — exactly the MeitY-style filename problem
    # described in the findings doc.
    neutral_url = "https://egazette.gov.in/WriteReadData/2025/268455.pdf"
    neutral_title = "Notification regarding office administration matters"
    assert not dd._match_keywords(neutral_title, neutral_url), \
        "test setup bug: title/url must not already contain a keyword"

    before = [_item("https://x.test/unrelated.pdf", "Some other notice")]
    after = before + [_item(neutral_url, neutral_title)]

    calls = {"n": 0}

    def fetch(**kwargs):
        calls["n"] += 1
        items = before if calls["n"] == 1 else after
        return {"items": items, "bucket_counts": {"src1": len(items)}}

    src = _source("src1", fetch)
    corrigendum_bytes = CORRIGENDUM_PDF.read_bytes()

    with patch.object(dd, "DISCOVERY_SOURCES", [src]), \
         patch.object(dd, "_download_pdf_bytes", return_value=corrigendum_bytes):
        dd.discover_all(conn, [])  # baseline (corrigendum not listed yet)
        new_documents, baseline_notes = dd.discover_all(conn, [])  # now it's listed

    assert baseline_notes == []
    assert len(new_documents) == 1
    doc = new_documents[0]
    assert doc["url"] == neutral_url
    assert doc["title"] == neutral_title
    assert doc["unreadable"] is False
    assert doc["text_excerpt"], "excerpt must be captured from the PDF text"
    assert "corrigend" in doc["text_excerpt"].lower() or "892" in doc["text_excerpt"]
    assert any(kw.lower() in ("corrigend", "g.s.r. 846") for kw in (m.lower() for m in doc["matched_keywords"]))


# --------------------------------------------------------------------------
# 4: relevance rules — all_items_relevant vs keyword-gated
# --------------------------------------------------------------------------

def test_irrelevant_document_alerts_only_when_source_is_all_items_relevant(conn):
    def make(name: str, all_relevant: bool):
        calls = {"n": 0}

        def fetch(**kwargs):
            calls["n"] += 1
            old = [_item(f"https://x.test/{name}-old.html", "Old baseline doc")]
            if calls["n"] == 1:
                items = old
            else:
                items = old + [_item(f"https://x.test/{name}-new.html", "Totally unrelated announcement")]
            return {"items": items, "bucket_counts": {name: len(items)}}

        return _source(name, fetch, all_items_relevant=all_relevant)

    with patch.object(dd, "DISCOVERY_SOURCES", [make("src-normal", False)]):
        dd.discover_all(conn, [])
        new_docs_normal, _ = dd.discover_all(conn, [])
    with patch.object(dd, "DISCOVERY_SOURCES", [make("src-relevant", True)]):
        dd.discover_all(conn, [])
        new_docs_relevant, _ = dd.discover_all(conn, [])

    assert new_docs_normal == []
    row = conn.execute(
        "SELECT alerted FROM discovered_documents WHERE url = ?", ("https://x.test/src-normal-new.html",)
    ).fetchone()
    assert row is not None and row["alerted"] == 0, "must still be stored, just not alerted"

    assert len(new_docs_relevant) == 1
    assert new_docs_relevant[0]["url"] == "https://x.test/src-relevant-new.html"


# --------------------------------------------------------------------------
# 5: an unreadable new PDF is alerted, never dropped
# --------------------------------------------------------------------------

def test_unreadable_new_pdf_is_alerted_not_dropped(conn):
    url = "https://x.test/broken.pdf"
    calls = {"n": 0}

    def fetch(**kwargs):
        calls["n"] += 1
        items = [] if calls["n"] == 1 else [_item(url, "A notice with no keywords in its title")]
        return {"items": items, "bucket_counts": {"src1": len(items)}}

    src = _source("src1", fetch)

    with patch.object(dd, "DISCOVERY_SOURCES", [src]), \
         patch.object(dd, "_download_pdf_bytes", side_effect=RuntimeError("simulated download failure")):
        dd.discover_all(conn, [])  # baseline (0 items)
        new_documents, _ = dd.discover_all(conn, [])

    assert len(new_documents) == 1
    assert new_documents[0]["url"] == url
    assert new_documents[0]["unreadable"] is True
    row = conn.execute("SELECT text_excerpt FROM discovered_documents WHERE url = ?", (url,)).fetchone()
    assert row["text_excerpt"] == dd.UNREADABLE_MARKER


# --------------------------------------------------------------------------
# 6: canary — a broken listing must not look like "nothing new"
# --------------------------------------------------------------------------

def test_canary_flags_zero_items_and_a_big_drop(conn):
    conn.execute(
        "INSERT INTO discovery_run_log (discovery_source, run_date, items_found) VALUES (?, ?, ?)",
        ("bucketA", "2026-09-29", 10),
    )
    conn.execute(
        "INSERT INTO discovery_run_log (discovery_source, run_date, items_found) VALUES (?, ?, ?)",
        ("bucketB", "2026-09-29", 8),
    )
    conn.commit()

    def fetch(**kwargs):
        # bucketA: dropped to 0. bucketB: dropped to 3, which is < 50% of 8.
        return {"items": [], "bucket_counts": {"bucketA": 0, "bucketB": 3}}

    src = _source("src1", fetch)
    errors: list[str] = []
    with patch.object(dd, "DISCOVERY_SOURCES", [src]):
        dd.discover_all(conn, errors)

    assert any("bucketA" in e for e in errors)
    assert any("bucketB" in e for e in errors)


def test_canary_does_not_flag_a_fresh_or_previously_empty_bucket(conn):
    """A month bucket with no prior row (or whose only prior row was 0) must
    not be flagged — the 1st of a new month is legitimately thin/empty, and
    flagging it every month would be a false alarm, not a real problem."""

    def fetch(**kwargs):
        return {"items": [], "bucket_counts": {"brand-new-bucket": 0}}

    src = _source("src1", fetch)
    errors: list[str] = []
    with patch.object(dd, "DISCOVERY_SOURCES", [src]):
        dd.discover_all(conn, errors)

    assert errors == []


# --------------------------------------------------------------------------
# 7: one source failing must not stop the others
# --------------------------------------------------------------------------

def test_one_source_exception_does_not_stop_the_others(conn):
    def bad_fetch(**kwargs):
        raise RuntimeError("simulated source failure")

    bad = _source("bad-source", bad_fetch)
    good = _source("good-source", _static_fetch("good-source", [_item("https://x.test/ok.html", "Fine")]))

    errors: list[str] = []
    with patch.object(dd, "DISCOVERY_SOURCES", [bad, good]):
        new_documents, baseline_notes = dd.discover_all(conn, errors)

    assert any("bad-source" in e and "simulated source failure" in e for e in errors)
    assert baseline_notes == ["baseline captured for good-source: 1 document(s)"]


# --------------------------------------------------------------------------
# 8: a failed send must never lose an alert
# --------------------------------------------------------------------------

def test_failed_send_leaves_alerted_zero_and_is_retried_next_run(conn):
    url = "https://x.test/new.html"
    calls = {"n": 0}

    def fetch(**kwargs):
        calls["n"] += 1
        items = [] if calls["n"] == 1 else [_item(url, "DPDP related notice")]
        return {"items": items, "bucket_counts": {"src1": len(items)}}

    src = _source("src1", fetch, all_items_relevant=True)

    with patch.object(dd, "DISCOVERY_SOURCES", [src]):
        dd.discover_all(conn, [])  # baseline
        new_documents, _ = dd.discover_all(conn, [])
        assert len(new_documents) == 1

        # simulate a failed send: mark_alerted() is deliberately not called
        row = conn.execute("SELECT alerted FROM discovered_documents WHERE url = ?", (url,)).fetchone()
        assert row["alerted"] == 0

        # next run must offer it again, not treat it as already handled
        new_documents_2, _ = dd.discover_all(conn, [])
        assert len(new_documents_2) == 1
        assert new_documents_2[0]["url"] == url

        # now simulate a successful send
        dd.mark_alerted(conn, [url])
        row2 = conn.execute("SELECT alerted FROM discovered_documents WHERE url = ?", (url,)).fetchone()
        assert row2["alerted"] == 1

        # a further run must not re-alert it
        new_documents_3, _ = dd.discover_all(conn, [])
        assert new_documents_3 == []


# --------------------------------------------------------------------------
# 9: email subject/body
# --------------------------------------------------------------------------

class _FakeSMTP:
    def __init__(self, sent: dict):
        self._sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, *a, **k):
        pass

    def send_message(self, msg):
        self._sent["msg"] = msg


def test_email_subject_and_body_for_new_documents(monkeypatch):
    import notify

    monkeypatch.setattr(notify, "GMAIL_ADDRESS", "sender@example.test")
    monkeypatch.setattr(notify, "GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setattr(notify, "NOTIFY_EMAIL", "recipient@example.test")

    new_documents = [{
        "url": "https://egazette.gov.in/WriteReadData/2025/268455.pdf",
        "title": "Notification Extraordinary of Corrigendum to the Digital Personal Data Protection Rules 2025",
        "discovery_source": "egazette-meity",
        "published_date": "2025-12-11",
        "matched_keywords": ["corrigend", "G.S.R. 846"],
        "text_excerpt": "G.S.R. 892(E). In the notification of the Government of India...",
        "unreadable": False,
    }]
    baseline_notes = ["baseline captured for egazette-meity: 3 document(s)"]

    sent: dict = {}
    with patch.object(notify.smtplib, "SMTP_SSL", return_value=_FakeSMTP(sent)):
        notify.send_summary([], [], 4, 4, new_documents=new_documents, baseline_notes=baseline_notes)

    msg = sent["msg"]
    assert msg["Subject"].startswith("ACTION NEEDED — new DPDP-related document found")
    body = msg.get_content()
    assert "Notification Extraordinary of Corrigendum" in body
    assert "egazette.gov.in/WriteReadData/2025/268455.pdf" in body
    assert "Nothing has been changed in the database — please review this document." in body
    assert "baseline captured for egazette-meity" in body
    assert list(msg.iter_attachments()) == [], "no regulatory changes were applied — nothing should be attached"


def test_email_unchanged_when_there_are_no_new_documents(monkeypatch):
    import notify

    monkeypatch.setattr(notify, "GMAIL_ADDRESS", "sender@example.test")
    monkeypatch.setattr(notify, "GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setattr(notify, "NOTIFY_EMAIL", "recipient@example.test")

    sent: dict = {}
    with patch.object(notify.smtplib, "SMTP_SSL", return_value=_FakeSMTP(sent)):
        notify.send_summary([], [], 4, 4)

    msg = sent["msg"]
    today = date.today().isoformat()
    assert msg["Subject"] == f"DPDP Monitor — No changes detected today ({today})"
    assert "ACTION NEEDED" not in msg["Subject"]


# --------------------------------------------------------------------------
# 10: schema migration is additive only
# --------------------------------------------------------------------------

def test_schema_migration_adds_new_tables_without_touching_existing_data(tmp_path):
    """
    Uses a copy of the real committed database, but deliberately drops the
    two new tables from the copy first rather than assuming the committed
    db doesn't have them yet — it now legitimately does, since the daily
    pipeline's own init_schema() call already upgraded the real db/dpdpa.db
    in production. Dropping them here makes this test meaningful regardless
    of that (and still proves nothing else gets touched).
    """
    import shutil

    from db import DB_PATH, get_connection, init_schema

    copy_path = tmp_path / "dpdpa_copy.db"
    shutil.copy(DB_PATH, copy_path)

    connection = get_connection(copy_path)
    try:
        connection.execute("DROP TABLE IF EXISTS discovered_documents")
        connection.execute("DROP TABLE IF EXISTS discovery_run_log")
        connection.commit()

        counts_before = {
            table: connection.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            for table in ("provisions", "change_log", "source_log", "source_snapshot")
        }

        init_schema(connection)

        for table, before in counts_before.items():
            after = connection.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            assert after == before, f"{table} row count changed after init_schema()"

        tables_after = {
            r["name"] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "discovered_documents" in tables_after
        assert "discovery_run_log" in tables_after
        for table in ("discovered_documents", "discovery_run_log"):
            assert connection.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"] == 0

        # Idempotent even once the tables already have real rows — a second
        # init_schema() call (exactly what happens every pipeline run) must
        # never reset or drop what's already been discovered.
        connection.execute(
            "INSERT INTO discovered_documents (url, discovery_source, first_seen_date) "
            "VALUES ('https://x.test/probe.pdf', 'probe', '2026-01-01')"
        )
        connection.commit()
        init_schema(connection)
        assert connection.execute(
            "SELECT COUNT(*) c FROM discovered_documents WHERE url = 'https://x.test/probe.pdf'"
        ).fetchone()["c"] == 1
    finally:
        connection.close()
