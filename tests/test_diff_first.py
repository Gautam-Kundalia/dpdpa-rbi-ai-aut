"""
Phase 8: the diff-first classification design (Phase 6) — baseline capture,
changed-passage extraction, dropping mostly-Hindi passages, and the PIB
keyword filter. No live API calls in this file (that's covered separately,
sparingly, given the API budget).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import classify_change as cc

from conftest import FakeFetchResult, seed_source_log


# --------------------------------------------------------------------------
# Baseline capture
# --------------------------------------------------------------------------

def test_no_snapshot_yet_stores_one_and_makes_no_ai_call(conn):
    seed_source_log(conn, document_id="SRC-0001")
    fr = FakeFetchResult(document_id="SRC-0001", content_text="Rule 1. Short title.", content_hash="h1")

    with patch.object(cc, "_call_claude") as mock_claude:
        result = cc.classify(fr, conn)

    assert result == []
    mock_claude.assert_not_called()
    row = conn.execute("SELECT content_hash, content_text FROM source_snapshot WHERE document_id = ?",
                        ("SRC-0001",)).fetchone()
    assert row["content_hash"] == "h1"
    assert row["content_text"] == "Rule 1. Short title."


def test_unchanged_hash_against_existing_snapshot_is_a_noop(conn):
    seed_source_log(conn, document_id="SRC-0001")
    conn.execute(
        "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) VALUES (?,?,?,date('now'))",
        ("SRC-0001", "h1", "Rule 1. Short title."),
    )
    conn.commit()
    fr = FakeFetchResult(document_id="SRC-0001", content_text="Rule 1. Short title.", content_hash="h1")

    with patch.object(cc, "_call_claude") as mock_claude:
        result = cc.classify(fr, conn)

    assert result == []
    mock_claude.assert_not_called()


# --------------------------------------------------------------------------
# Changed-passage extraction (hunking)
# --------------------------------------------------------------------------

def test_diff_hunks_isolate_the_changed_line_with_context():
    old = "Rule 1. Short title.\nRule 2. Definitions.\nRule 3. Applicability."
    new = "Rule 1. Short title, extent and commencement.\nRule 2. Definitions.\nRule 3. Applicability."
    hunks = cc._diff_hunks(old, new)
    assert len(hunks) == 1
    rendered = hunks[0].render()
    assert "-Rule 1. Short title." in rendered
    assert "+Rule 1. Short title, extent and commencement." in rendered
    assert "Rule 2. Definitions." in rendered  # context line


def test_render_diff_caps_at_max_chars():
    old = "x"
    new = "y" * 30_000
    hunks = cc._diff_hunks(old, new)
    rendered = cc._render_diff(hunks, max_chars=1000)
    assert len(rendered) <= 1000 + len("\n\n[...diff truncated at 1000 characters...]")
    assert "truncated" in rendered


# --------------------------------------------------------------------------
# Hindi-dropping — at line granularity, not whole-hunk (see classify_change.py)
# --------------------------------------------------------------------------

def test_hindi_only_change_is_dropped_entirely():
    old = "यह एक पंक्ति है।"
    new = "यह एक बदली हुई हिंदी पंक्ति है जो पूरी तरह से अलग शब्दों के साथ है।"
    hunks = cc._diff_hunks(old, new)
    kept, dropped = cc._drop_hindi_hunks(hunks)
    assert kept == []
    assert dropped > 0


def test_english_change_survives_next_to_unrelated_hindi_context():
    old = "Rule 1. Short title.\nRule 2. Definitions.\nयह एक हिंदी पंक्ति है जो नहीं बदली।"
    new = ("Rule 1. Short title, extent and commencement.\nRule 2. Definitions.\n"
           "यह एक हिंदी पंक्ति है जो बदल गई अब बहुत अलग है पूरी तरह से नया पाठ यहाँ जोड़ा गया।")
    hunks = cc._diff_hunks(old, new)
    kept, dropped = cc._drop_hindi_hunks(hunks)
    assert dropped > 0, "the Hindi line should have been dropped"
    assert len(kept) == 1
    rendered = kept[0].render()
    assert "Short title, extent and commencement" in rendered
    assert "हिंदी" not in rendered, "Hindi content must not leak into what's kept"


# --------------------------------------------------------------------------
# PIB keyword pre-filter
# --------------------------------------------------------------------------

def test_pib_relevant_title_is_kept():
    old = "Some unrelated release\nAnother one"
    new = "Some unrelated release\nAnother one\nMeitY notifies Digital Personal Data Protection Rules amendment"
    hunks = cc._diff_hunks(old, new)
    relevant = cc._pib_relevant_hunks(hunks)
    assert len(relevant) == 1


def test_pib_irrelevant_titles_are_all_dropped():
    old = "Some unrelated release\nAnother one"
    new = "Some unrelated release\nAnother one\nMinister inaugurates a new bridge"
    hunks = cc._diff_hunks(old, new)
    relevant = cc._pib_relevant_hunks(hunks)
    assert relevant == []


def test_pib_source_with_no_relevant_titles_is_no_change_no_ai_call(conn):
    seed_source_log(conn, document_id="SRC-0001", source="PIB")
    conn.execute(
        "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) VALUES (?,?,?,date('now'))",
        ("SRC-0001", "h1", "Minister inaugurates a bridge"),
    )
    conn.commit()
    fr = FakeFetchResult(source="PIB", document_id="SRC-0001",
                          content_text="Minister inaugurates a bridge\nAnother unrelated release",
                          content_hash="h2")

    with patch.object(cc, "_call_claude") as mock_claude:
        result = cc.classify(fr, conn)

    assert result == []
    mock_claude.assert_not_called()
    status = conn.execute("SELECT processing_status FROM source_log WHERE document_id = ?", ("SRC-0001",)).fetchone()
    assert status["processing_status"] == "No Change Detected"


# --------------------------------------------------------------------------
# Provision-number matching
# --------------------------------------------------------------------------

def test_match_provisions_by_number_in_changed_text():
    provisions = [
        {"provision_id": "DPDPR-R23", "reference": "Rule 23(1)"},
        {"provision_id": "DPDPA-S6.1_8_10", "reference": "Section 6"},
    ]
    old = "An appeal under sub-rule (5) of rule 23 shall be filed within such time and in such."
    new = "An appeal under sub-rule (5) of rule 23 shall be filed within such time and in such order."
    hunks = cc._diff_hunks(old, new)
    matched = cc._match_provisions_by_number(hunks, provisions)
    assert [p["provision_id"] for p in matched] == ["DPDPR-R23"]


def test_no_number_found_means_no_provisions_matched():
    provisions = [{"provision_id": "DPDPR-R23", "reference": "Rule 23(1)"}]
    old = "some generic text."
    new = "some different generic text."
    hunks = cc._diff_hunks(old, new)
    matched = cc._match_provisions_by_number(hunks, provisions)
    assert matched == []
