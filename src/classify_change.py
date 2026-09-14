"""
Classify a changed source's content against current `provisions` using
OpenRouter, returning strict JSON matching the change_log schema fields.

Usage:
    from classify_change import classify
    changes = classify(fetch_result, conn)   # list[dict], possibly empty
"""
from __future__ import annotations

import json
import os

import requests
from dotenv import load_dotenv

from db import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

VALID_CHANGE_TYPES = {"New Provision", "Amendment", "Repeal", "Clarification", "Correction"}

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

Respond with ONLY a JSON object of the exact shape:
{"changes": [{"provision_id": "...", "change_type": "...", "old_value_summary": "...", \
"new_value_summary": "...", "old_full_text": "..." or null, "new_full_text": "..." or null, \
"confidence_score": 0.0}]}
No prose, no markdown fences — just the JSON object. If there is no real change, respond with \
{"changes": []}.
"""


def _current_provisions(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT provision_id, reference, topic_category, current_summary, full_text "
        "FROM provisions ORDER BY sort_order"
    ).fetchall()
    return [dict(r) for r in rows]


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


def _call_openrouter(user_prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set (check .env / GitHub secret)")
    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


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
    Classify one changed source. Returns a validated list of change dicts
    (possibly empty). On a parse/validation failure, retries once; if it
    still fails, marks source_log.processing_status='Error' for this
    source's document_id and returns [] (skip auto-apply for that item).
    """
    provisions = _current_provisions(conn)
    user_prompt = _build_user_prompt(fetch_result, provisions)

    last_error = None
    for attempt in range(2):
        try:
            raw_response = _call_openrouter(user_prompt)
            parsed = json.loads(raw_response)
            return _validate(parsed, provisions)
        except Exception as exc:
            last_error = exc
            print(f"[classify_change] attempt {attempt + 1} failed for {fetch_result.document_id}: {exc}")

    conn.execute(
        "UPDATE source_log SET processing_status = 'Error' WHERE document_id = ?",
        (fetch_result.document_id,),
    )
    conn.commit()
    print(f"[classify_change] giving up on {fetch_result.document_id} after retry: {last_error}")
    return []
