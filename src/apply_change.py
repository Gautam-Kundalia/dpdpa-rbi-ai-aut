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


def apply(change: dict, fetch_result, conn, model_name: str) -> str:
    """
    Insert `change` into change_log, then apply it to `provisions`:
      - New Provision -> insert a new provisions row
      - Amendment/Clarification/Correction -> update full_text/current_summary
      - Repeal -> update status to 'Repealed' (full_text kept for record)
    Returns the new change_id.
    """
    now = datetime.now(timezone.utc).isoformat()
    change_id = next_id(conn, "change_log", "change_id", "CHG")
    provision_id = change["provision_id"]

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

    today = now[:10]
    existing = conn.execute(
        "SELECT provision_id FROM provisions WHERE provision_id = ?", (provision_id,)
    ).fetchone()

    if change["change_type"] == "New Provision" or not existing:
        docx_path = _docx_path_for(provision_id)
        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM provisions WHERE full_text_path = ?",
            (docx_path,),
        ).fetchone()[0]
        instrument_type = "Rule" if provision_id.startswith("DPDPR-") else "Act Section"
        conn.execute(
            """INSERT INTO provisions
               (provision_id, instrument_type, reference, topic_category, current_summary,
                full_text, full_text_path, full_text_anchor, sort_order, status,
                effective_date, last_updated_date, source_document, source_url,
                confidence_score, review_status, reviewed_by, review_date,
                latest_change_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?, ?, ?, ?, ?, 'Confirmed', 'auto', ?, ?, ?)""",
            (
                provision_id,
                instrument_type,
                change.get("new_value_summary") or provision_id,
                None,
                change["new_value_summary"],
                change["new_full_text"],
                docx_path,
                _make_anchor(provision_id),
                max_sort + 1,
                today,
                today,
                fetch_result.title,
                fetch_result.url,
                change["confidence_score"],
                today,
                change_id,
                "Auto-created from detected change — no human review gate.",
            ),
        )
    elif change["change_type"] == "Repeal":
        conn.execute(
            """UPDATE provisions
               SET status = 'Repealed', current_summary = ?, last_updated_date = ?,
                   latest_change_id = ?
               WHERE provision_id = ?""",
            (change["new_value_summary"], today, change_id, provision_id),
        )
    else:  # Amendment, Clarification, Correction
        conn.execute(
            """UPDATE provisions
               SET full_text = ?, current_summary = ?, last_updated_date = ?,
                   latest_change_id = ?
               WHERE provision_id = ?""",
            (
                change["new_full_text"],
                change["new_value_summary"],
                today,
                change_id,
                provision_id,
            ),
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
