"""
Audit finding M-3: a third of the daily emails were error emails, and a routine
error email is one nobody reads — which is how the important one gets missed.

Two changes, both tested here:
  (a) a failed download is tried once more after a short pause, so a single
      slow moment on a government website is not an error at all;
  (b) an error that is the SAME problem as yesterday still appears in full in
      the email body, but stops counting towards the subject line until it has
      been going for three days. A NEW kind of error is always news.

Also covers L-5: attaching a file type nobody thought of must not crash the
whole email.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fetch_sources as fs
import notify
from notify import _build_body

from conftest import seed_source_log


# --------------------------------------------------------------------------
# (a) one retry before a download counts as a failure
# --------------------------------------------------------------------------

def test_a_download_that_works_on_the_second_try_is_not_an_error(conn):
    calls: list[str] = []

    def flaky(url):
        calls.append(url)
        if calls.count(url) == 1:
            raise TimeoutError("simulated slow moment")
        return b"<html><body>page content</body></html>"

    errors: list[str] = []
    with patch.object(fs, "_fetch_raw", side_effect=flaky), \
         patch.object(fs, "_extract_text", side_effect=lambda raw, kind: "page content"):
        changed = fs.fetch_all(conn, fetch_errors=errors)

    assert errors == [], f"a retry that succeeded must not be reported as a failure: {errors}"
    assert len(changed) == len(fs.SOURCES)
    assert len(calls) == 2 * len(fs.SOURCES), "each source should have been tried twice"


def test_a_download_that_fails_twice_is_still_an_error(conn):
    errors: list[str] = []
    with patch.object(fs, "_fetch_raw", side_effect=TimeoutError("still down")):
        fs.fetch_all(conn, fetch_errors=errors)
    assert len(errors) == len(fs.SOURCES)
    assert all("still down" in e for e in errors)


# --------------------------------------------------------------------------
# (b) counting how long the same problem has been going on
# --------------------------------------------------------------------------

def _fail_all(conn, day, errors, repeats):
    with patch.object(fs, "_fetch_raw", side_effect=TimeoutError("egazette is slow again")), \
         patch.object(fs, "date") as mock_date:
        mock_date.today.return_value.isoformat.return_value = day
        fs.fetch_all(conn, fetch_errors=errors, repeated_errors=repeats)


def test_the_same_problem_on_three_days_running_is_counted(conn):
    days = ["2026-10-01", "2026-10-02", "2026-10-03"]
    per_day = []
    for day in days:
        errors: list[str] = []
        repeats: list[str] = []
        _fail_all(conn, day, errors, repeats)
        per_day.append((errors, repeats))

    counted = [
        row["error_streak_days"]
        for row in conn.execute("SELECT error_streak_days FROM source_log ORDER BY document_id")
    ]
    assert set(counted) == {3}, counted

    # Day 1: news. Day 2: the same thing, so not subject-line news. Day 3: news
    # again, because by then it is not going to fix itself.
    assert per_day[0][1] == [], "day 1 is always news"
    assert len(per_day[1][1]) == len(fs.SOURCES), "day 2 is the same problem"
    assert per_day[2][1] == [], "day 3 is news again"
    # But the body always has everything.
    for errors, _repeats in per_day:
        assert len(errors) == len(fs.SOURCES)


def test_two_runs_on_the_same_day_do_not_count_twice(conn):
    for _ in range(2):
        _fail_all(conn, "2026-10-01", [], [])
    counted = [
        row["error_streak_days"]
        for row in conn.execute("SELECT error_streak_days FROM source_log")
    ]
    assert set(counted) == {1}, counted


def test_a_different_problem_starts_the_count_again(conn):
    _fail_all(conn, "2026-10-01", [], [])
    errors: list[str] = []
    repeats: list[str] = []
    with patch.object(fs, "_fetch_raw", side_effect=ValueError("a completely different fault")), \
         patch.object(fs, "date") as mock_date:
        mock_date.today.return_value.isoformat.return_value = "2026-10-02"
        fs.fetch_all(conn, fetch_errors=errors, repeated_errors=repeats)

    counted = {row["error_streak_days"] for row in conn.execute("SELECT error_streak_days FROM source_log")}
    assert counted == {1}, "a new kind of problem is day 1, not day 2"
    assert repeats == [], "a new kind of error is always news"


def test_a_successful_fetch_clears_the_count(conn):
    _fail_all(conn, "2026-10-01", [], [])
    with patch.object(fs, "_fetch_raw", return_value=b"ok"), \
         patch.object(fs, "_extract_text", side_effect=lambda raw, kind: "ok"):
        fs.fetch_all(conn)
    rows = conn.execute(
        "SELECT error_signature, error_streak_days FROM source_log"
    ).fetchall()
    assert all(r["error_signature"] is None and r["error_streak_days"] == 0 for r in rows)


# --------------------------------------------------------------------------
# what the email actually says
# --------------------------------------------------------------------------

def test_a_brand_new_error_is_on_the_subject_line():
    subject, body = _build_body([], ["fetch failed for eGazette: boom"], 3, 2)
    assert "1 error(s) today" in subject
    assert "fetch failed for eGazette: boom" in body


def test_yesterdays_error_again_is_in_the_body_but_not_shouted_about():
    same = "fetch failed for eGazette: boom [same problem for 2 days running]"
    subject, body = _build_body([], [same], 3, 2, repeated_errors=[same])
    assert "no new problems, 1 ongoing" in subject, subject
    assert same in body, "the body must still list it in full — nothing is hidden"
    assert "all of them the same as yesterday" in body


def test_a_new_error_alongside_an_old_one_still_counts_as_news():
    old = "fetch failed for eGazette: boom [same problem for 2 days running]"
    new = "fetch failed for MeitY: something else entirely"
    subject, body = _build_body([], [old, new], 3, 1, repeated_errors=[old])
    assert "1 error(s) today" in subject, subject
    assert old in body and new in body
    assert "1 new, 1 the same as yesterday" in body


def test_a_quiet_day_still_reads_as_a_quiet_day():
    subject, _body = _build_body([], [], 3, 3)
    assert "No changes detected today" in subject


# --------------------------------------------------------------------------
# L-5: an unknown attachment type must not break the email
# --------------------------------------------------------------------------

def test_an_unexpected_attachment_type_does_not_crash_the_email(tmp_path, monkeypatch):
    from email.message import EmailMessage

    odd = tmp_path / "surprise.pdf"
    odd.write_bytes(b"%PDF-1.4 not really a pdf")
    monkeypatch.setattr(notify, "ATTACHMENT_PATHS", [odd])

    msg = EmailMessage()
    msg["Subject"] = "t"
    msg["From"] = "a@b.test"
    msg["To"] = "c@d.test"
    msg.set_content("body")
    notify._attach_docs(msg)          # must not raise KeyError

    attached = list(msg.iter_attachments())
    assert len(attached) == 1
    assert attached[0].get_filename() == "surprise.pdf"
    assert attached[0].get_content_type() == "application/octet-stream", \
        "an unknown type falls back to 'some sort of file', never a crash"
