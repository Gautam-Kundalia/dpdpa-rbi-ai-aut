"""
Classify a changed source's content against current `provisions` using
Claude (forced tool-use), returning strict JSON matching the change_log
schema fields.

Usage:
    from classify_change import classify
    changes = classify(fetch_result, conn)   # list[dict], possibly empty
"""
from __future__ import annotations

import os

import anthropic
from dotenv import load_dotenv

from db import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

VALID_CHANGE_TYPES = {"New Provision", "Amendment", "Repeal", "Clarification", "Correction"}

# How many times to try the AI call before giving up on a source for
# this run. Originally sized against the free-tier OpenRouter model,
# which failed intermittently (~1-in-3 in a small sample) under this
# pipeline's large prompt. Kept at 3 as defense-in-depth for transient
# API/network failures even on Claude's enforced-schema tool-use path,
# where a malformed response is no longer expected.
MAX_CLASSIFY_ATTEMPTS = 3


class ClassificationFailed(Exception):
    """
    Raised by classify() when the AI call/response never became usable
    after MAX_CLASSIFY_ATTEMPTS tries. Fixes a real bug: the previous
    version swallowed this and returned [], indistinguishable from "AI
    genuinely found nothing." Now a real failure is a real, raised
    error that reaches run_pipeline.py's error list, exit code, and the
    summary email.
    """

SYSTEM_PROMPT = """You are a legal-text change detector for a DPDP (Digital Personal Data \
Protection) Act/Rules compliance tracker. You are given:
1. The full list of provisions currently on file (provision_id, reference, current summary).
2. Freshly fetched content from one of three official sources (PIB, MeitY, or eGazette).

Your job: decide whether the fetched content contains an actual, verbatim legal change to \
one or more of the listed provisions (a new provision, an amendment, a repeal, a \
clarification, or a correction) versus containing nothing new (e.g. an unrelated press \
release, a navigation page, a listing with no substantive legal text).

Rules you must follow exactly:
- Only report a change if you can quote VERBATIM clause text for it from the fetched content \
given to you. Never paraphrase, summarize, or invent legal text into old_full_text/new_full_text \
— those two fields must be exact substrings (or near-exact, whitespace-normalized) of text that \
actually appears in the fetched content or the provided current provisions.
- If the fetched content does not contain enough verbatim text to be confident of a real \
change, return an empty changes list. It is always better to report nothing than to \
fabricate or guess.
- change_type must be exactly one of: "New Provision", "Amendment", "Repeal", \
"Clarification", "Correction".
- provision_id must exactly match an existing provision_id from the list given to you, UNLESS \
change_type is "New Provision", in which case propose a new provision_id following the same \
naming convention you observe in the existing list (e.g. 'DPDPR-R24' for a new Rule 24).
- confidence_score is a float 0.0-1.0 reflecting how sure you are this is a real, verbatim, \
correctly-matched legal change.
- old_full_text should be the current provision's full_text (given to you) when change_type \
is Amendment/Repeal/Clarification/Correction, or null for New Provision.
- new_full_text is the verbatim new clause text from the fetched content (or null for Repeal).
- old_value_summary and new_value_summary are short plain-language one-liners (NOT verbatim \
clause text) describing what changed, for the human-facing view.
"""


def _current_provisions(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT provision_id, reference, topic_category, current_summary, full_text "
        "FROM provisions ORDER BY sort_order"
    ).fetchall()
    return [dict(r) for r in rows]


def _relevant_provisions(conn, fetch_result) -> list[dict]:
    """
    Narrow the provisions list to the relevant instrument when the source
    is a known single-instrument document, so we're not sending every Act
    section's text on a Rules-only fetch (and vice versa). Never truncates
    an individual provision's own text — only narrows which provisions are
    included at all.
    """
    all_provisions = _current_provisions(conn)
    if "2025/11" in fetch_result.url:      # MeitY Rules PDF
        prefix = "DPDPR-"
    elif "2024/06" in fetch_result.url:    # MeitY Act PDF
        prefix = "DPDPA-"
    else:                                   # PIB / eGazette: could be either
        return all_provisions
    filtered = [p for p in all_provisions if p["provision_id"].startswith(prefix)]
    return filtered or all_provisions   # fail open if the filter matches nothing


def _build_user_prompt(fetch_result, provisions: list[dict]) -> str:
    prov_lines = "\n".join(
        f"- {p['provision_id']} ({p['reference']}): {p['current_summary'] or ''}\n"
        f"  full_text: {(p['full_text'] or '')[:2000]}"
        for p in provisions
    )
    # Cap fetched content to keep the request reasonably sized.
    content = fetch_result.content_text[:60000]
    return (
        f"SOURCE: {fetch_result.source} — {fetch_result.title}\nURL: {fetch_result.url}\n\n"
        f"=== CURRENT PROVISIONS ON FILE ===\n{prov_lines}\n\n"
        f"=== FRESHLY FETCHED CONTENT ===\n{content}\n"
    )


CHANGES_TOOL = {
    "name": "report_changes",
    "description": "Report any real, verbatim legal changes found in the fetched content. Call this even if the list is empty.",
    "input_schema": {
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "provision_id": {"type": "string"},
                        "change_type": {"type": "string", "enum": sorted(VALID_CHANGE_TYPES)},
                        "old_value_summary": {"type": "string"},
                        "new_value_summary": {"type": "string"},
                        "old_full_text": {"type": ["string", "null"]},
                        "new_full_text": {"type": ["string", "null"]},
                        "confidence_score": {"type": "number"},
                    },
                    "required": ["provision_id", "change_type", "old_value_summary",
                                  "new_value_summary", "old_full_text", "new_full_text",
                                  "confidence_score"],
                },
            }
        },
        "required": ["changes"],
    },
}


def _call_claude(user_prompt: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (check .env / GitHub secret)")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[CHANGES_TOOL],
        tool_choice={"type": "tool", "name": "report_changes"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "report_changes":
            return block.input
    raise RuntimeError("Claude response had no report_changes tool_use block")


def _validate(parsed: dict, provisions: list[dict]) -> list[dict]:
    known_ids = {p["provision_id"] for p in provisions}
    changes = parsed.get("changes")
    if not isinstance(changes, list):
        raise ValueError("'changes' is not a list")

    validated = []
    for c in changes:
        required = {
            "provision_id", "change_type", "old_value_summary", "new_value_summary",
            "old_full_text", "new_full_text", "confidence_score",
        }
        missing = required - c.keys()
        if missing:
            raise ValueError(f"change entry missing fields: {missing}")
        if c["change_type"] not in VALID_CHANGE_TYPES:
            raise ValueError(f"invalid change_type: {c['change_type']}")
        if c["change_type"] != "New Provision" and c["provision_id"] not in known_ids:
            raise ValueError(f"unknown provision_id: {c['provision_id']}")
        if not isinstance(c["confidence_score"], (int, float)):
            raise ValueError("confidence_score must be numeric")
        validated.append(c)
    return validated


def classify(fetch_result, conn) -> list[dict]:
    """
    Classify one changed source. Returns a validated list of change dicts —
    an empty list is a legitimate success meaning the AI found no real
    change. On a parse/validation failure, retries up to
    MAX_CLASSIFY_ATTEMPTS times; if it still fails, marks
    source_log.processing_status='Error' for this source's document_id and
    raises ClassificationFailed (it does NOT return [] — that would be
    indistinguishable from a genuine "no change" result).
    """
    provisions = _relevant_provisions(conn, fetch_result)
    user_prompt = _build_user_prompt(fetch_result, provisions)

    last_error = None
    last_raw = None
    for attempt in range(MAX_CLASSIFY_ATTEMPTS):
        parsed = None
        try:
            parsed = _call_claude(user_prompt)
            return _validate(parsed, provisions)
        except Exception as exc:
            last_error = exc
            last_raw = parsed
            print(f"[classify_change] attempt {attempt + 1} failed for {fetch_result.document_id}: {exc}")

    conn.execute(
        "UPDATE source_log SET processing_status = 'Error' WHERE document_id = ?",
        (fetch_result.document_id,),
    )
    conn.commit()
    # last_raw is a dict (Claude's tool_use.input) or None, not a raw string —
    # str() it before slicing so a shape/validation failure (_validate raised
    # after a successful, well-formed tool call) still shows what came back.
    raw_snippet = f" — raw model output: {str(last_raw)[:300]!r}" if last_raw else ""
    print(f"[classify_change] giving up on {fetch_result.document_id} after {MAX_CLASSIFY_ATTEMPTS} attempts: {last_error}{raw_snippet}")
    raise ClassificationFailed(
        f"could not get a valid classification for {fetch_result.document_id} "
        f"({fetch_result.source} — {fetch_result.url}) after {MAX_CLASSIFY_ATTEMPTS} attempts: {last_error!r}{raw_snippet}"
    ) from last_error
