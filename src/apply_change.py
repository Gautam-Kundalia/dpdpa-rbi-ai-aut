"""
Apply a classified change: insert it into change_log (auto-approved — no
human review gate, per project decision) and update `provisions` to match.
Also marks the originating source_log row as Processed.

Usage:
    from apply_change import apply
    change_id = apply(change_dict, fetch_result, conn)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from db import next_id

DETECTED_BY_PREFIX = "agent:anthropic"


def _make_anchor(provision_id: str) -> str:
    anchor = re.sub(r"[^A-Za-z0-9_]", "_", provision_id)
    if not anchor[0].isalpha():
        anchor = "P_" + anchor
    return anchor[:40]


def _docx_path_for(provision_id: str) -> str:
    if provision_id.startswith("DPDPR-"):
        return "docs/DPDP_Rules_2025.docx"
    return "docs/DPDP_Act_2023.docx"


def _instrument_type_for(provision_id: str) -> str:
    if "-SCH" in provision_id:
        return "Schedule"
    if provision_id.startswith("DPDPR-"):
        return "Rule"
    return "Act Section"


_REFERENCE_PATTERN = re.compile(r"^DPDP[AR]-(SCH|R|S)(\S+)$")
_REFERENCE_LABELS = {"SCH": "Schedule", "R": "Rule", "S": "Section"}


def _derive_reference(provision_id: str) -> str:
    """
    'DPDPR-R24' -> 'Rule 24', 'DPDPA-S45' -> 'Section 45',
    'DPDPR-SCH8' -> 'Schedule 8'. Falls back to the raw provision_id for any
    shape this doesn't recognise, rather than guessing.
    """
    m = _REFERENCE_PATTERN.match(provision_id)
    if not m:
        return provision_id
    kind, num = m.group(1), m.group(2)
    return f"{_REFERENCE_LABELS[kind]} {num}"


def apply(change: dict, fetch_result, conn, model_name: str) -> str:
    """
    Insert `change` into change_log, then apply it to `provisions`:
      - New Provision -> insert a new provisions row, Pending Review,
        effective_date left NULL (commencement isn't known from a bare
        detected change — see the note it's given)
      - Amendment/Clarification/Correction -> replace ONLY the
        old_full_text span inside the provision's full_text (never the
        whole provision — a change_log row can be one clause out of a
        much longer section). Refuses (raises, applies nothing) unless
        that span appears in the current full_text EXACTLY once.
        current_summary is deliberately left untouched: the "what changed"
        line belongs in change_log only, never overwriting a provision's
        existing plain-language summary.
      - Repeal -> update status to 'Repealed' (full_text and
        current_summary both kept for the record, untouched)
    Returns the new change_id.
    """
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]
    change_id = next_id(conn, "change_log", "change_id", "CHG")
    provision_id = change["provision_id"]

    existing = conn.execute(
        "SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)
    ).fetchone()
    is_new = change["change_type"] == "New Provision" or not existing

    # Validate BEFORE writing anything — change_log has a FOREIGN KEY on
    # provision_id, so for an existing provision we must also know the
    # write will succeed before inserting change_log (a New Provision row
    # is inserted into `provisions` first, below, specifically so that FK
    # is satisfied when change_log is inserted afterwards).
    new_text = None
    if not is_new and change["change_type"] != "Repeal":
        current_text = existing["full_text"] or ""
        old_span = change["old_full_text"] or ""
        match_count = current_text.count(old_span) if old_span else 0
        if match_count != 1:
            raise ValueError(
                f"apply_change: old_full_text for {provision_id} matches the current "
                f"full_text {match_count} time(s) (need exactly 1) — refusing to apply, "
                f"nothing written for this change."
            )
        new_text = current_text.replace(old_span, change["new_full_text"] or "", 1)

    if is_new:
        docx_path = _docx_path_for(provision_id)
        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM provisions WHERE full_text_path = ?",
            (docx_path,),
        ).fetchone()[0]
        instrument_type = _instrument_type_for(provision_id)
        reference = _derive_reference(provision_id)
        conn.execute(
            """INSERT INTO provisions
               (provision_id, instrument_type, reference, topic_category, current_summary,
                full_text, full_text_path, full_text_anchor, sort_order, status,
                effective_date, last_updated_date, source_document, source_url,
                confidence_score, review_status, reviewed_by, review_date,
                latest_change_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', NULL, ?, ?, ?, ?, 'Pending Review', 'auto', ?, ?, ?)""",
            (
                provision_id,
                instrument_type,
                reference,
                None,
                change["new_value_summary"],
                change["new_full_text"],
                docx_path,
                _make_anchor(provision_id),
                max_sort + 1,
                today,
                fetch_result.title,
                fetch_result.url,
                change["confidence_score"],
                today,
                change_id,
                "Auto-created from detected change — no human review gate. "
                "Commencement to be confirmed from the notification.",
            ),
        )

    conn.execute(
        """INSERT INTO change_log
           (change_id, detected_timestamp, provision_id, change_type, change_origin,
            old_value_summary, new_value_summary, old_full_text, new_full_text,
            source_document, source_url, detected_by, confidence_score,
            review_status, reviewed_by, review_date, applied_to_master, notes)
           VALUES (?, ?, ?, ?, 'regulatory', ?, ?, ?, ?, ?, ?, ?, ?, 'Approved', 'auto', ?, 'Y', ?)""",
        (
            change_id,
            now,
            provision_id,
            change["change_type"],
            change["old_value_summary"],
            change["new_value_summary"],
            change["old_full_text"],
            change["new_full_text"],
            fetch_result.title,
            fetch_result.url,
            f"{DETECTED_BY_PREFIX}/{model_name}",
            change["confidence_score"],
            now,
            "Auto-applied — no human review gate (project decision).",
        ),
    )

    if not is_new:
        if change["change_type"] == "Repeal":
            conn.execute(
                """UPDATE provisions
                   SET status = 'Repealed', last_updated_date = ?, latest_change_id = ?
                   WHERE provision_id = ?""",
                (today, change_id, provision_id),
            )
        else:  # Amendment, Clarification, Correction — replace only the changed span.
            # current_summary is deliberately NOT touched here: the "what
            # changed" line belongs in change_log only, never overwriting a
            # provision's existing plain-language summary.
            conn.execute(
                """UPDATE provisions
                   SET full_text = ?, last_updated_date = ?, latest_change_id = ?
                   WHERE provision_id = ?""",
                (new_text, today, change_id, provision_id),
            )

    row = conn.execute(
        "SELECT linked_change_ids FROM source_log WHERE document_id = ?",
        (fetch_result.document_id,),
    ).fetchone()
    prior_links = row["linked_change_ids"] if row and row["linked_change_ids"] else ""
    linked = ",".join(filter(None, [prior_links, change_id]))
    conn.execute(
        "UPDATE source_log SET processing_status = 'Processed', linked_change_ids = ? WHERE document_id = ?",
        (linked, fetch_result.document_id),
    )

    conn.commit()
    return change_id
