"""
Classify a changed source's content against current `provisions` using
Claude (forced tool-use), returning strict JSON matching the change_log
schema fields.

Diff-first design (Phase 6, 23 Sep 2026 audit): instead of sending the
model the whole fetched document every time, we keep a snapshot of the
text from the last successfully classified fetch of each source
(source_snapshot table) and diff the new fetch against it in plain Python
first. Only the changed passages — plus the provisions they plausibly
touch — go to the model. This fixes several real production failures in
one go: the Act PDF's max_tokens failure (the model was being asked to
report differences across the *whole* 48-section document every time,
because the prompt was always the full text, not just what changed), the
60,000-character cutoff that silently dropped Sections 43/44/the Schedule
from every Act prompt, and the Rules PDF classifier only ever seeing the
Hindi half of a 120,000-character bilingual document (the English text
starts past the old cutoff).

Usage:
    from classify_change import classify
    changes = classify(fetch_result, conn)   # list[dict], possibly empty
"""
from __future__ import annotations

import difflib
import os
import re

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

MAX_PROMPT_CHARS = 20_000
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
HINDI_DROP_THRESHOLD = 0.30

# Only these titles get sent to the model at all for the PIB source — the
# rest of a press-release feed is never going to be a DPDP change, and
# every avoided call is avoided cost and avoided noise.
PIB_RELEVANCE_RE = re.compile(
    r"data protection|DPDP|personal data|MeitY|Electronics and Information Technology"
    r"|Data Protection Board",
    re.IGNORECASE,
)

# provision.reference numbers we can match against numbers found in a
# changed passage, e.g. "Rule 23(1)" ~ "23", "Section 6(9)" ~ "6".
SECTION_OR_RULE_NUM_RE = re.compile(
    r"\b(?:section|rule|sub-section|clause|schedule)\s+(\d+[A-Za-z]?)\b", re.IGNORECASE
)
REFERENCE_LEADING_NUM_RE = re.compile(r"(\d+)")


class ClassificationFailed(Exception):
    """
    Raised by classify() when the AI call/response never became usable
    after MAX_CLASSIFY_ATTEMPTS tries. Fixes a real bug: an earlier version
    swallowed this and returned [], indistinguishable from "AI genuinely
    found nothing." Now a real failure is a real, raised error that reaches
    run_pipeline.py's error list, exit code, and the summary email — and
    (Phase 5) causes the source's fingerprint to be rolled back so the next
    run retries instead of silently giving up.
    """


SYSTEM_PROMPT = """You are a legal-text change detector for a DPDP (Digital Personal Data \
Protection) Act/Rules compliance tracker.

You are being shown a DIFF — the changed passages between the last time we successfully \
checked one of three official sources (PIB, MeitY, or eGazette) and right now — NOT the whole \
document. Lines starting with "-" were in the old fetch and are gone or changed; lines \
starting with "+" are new or changed in the current fetch; unmarked lines are unchanged \
context shown around a change. You are also given the current text on file for the \
provisions this changed passage plausibly relates to (or, if none could be matched by number, \
the list of all provision IDs and references with no text, so you can still identify a \
brand-new provision).

Your ONLY job: decide whether this diff shows the GOVERNMENT actually changing the law or \
rules — a new provision, an amendment, a repeal, a clarification, or an official corrigendum \
(use "Correction" ONLY for an official corrigendum correcting a printing error in a prior \
Gazette notification — never for anything else) — versus the diff being noise (an unrelated \
press release, a page-layout change, content reordering, a navigation change) or being \
different from our current text for some reason that ISN'T the government's doing.

Rules you must follow exactly:
- You are comparing the OLD FETCH to the NEW FETCH (both from the same official source, shown \
in the diff). You are NOT comparing our stored provisions text to the new fetch — a provision's \
current full_text may legitimately differ from source wording for reasons that have nothing to \
do with a government change (paraphrase history, formatting), and that is never your call to \
flag. Report a change only when the diff itself shows the source's own content changing.
- Only report a change if you can quote VERBATIM clause text for it from the diff's "+" \
(new/changed) lines. Never paraphrase, summarize, or invent legal text into old_full_text/ \
new_full_text — those two fields must be exact substrings (or near-exact, whitespace- \
normalized) of text that actually appears in the diff or the provided current provisions.
- If the diff does not contain enough verbatim text to be confident of a real government \
change, return an empty changes list. It is always better to report nothing than to \
fabricate or guess.
- change_type must be exactly one of: "New Provision", "Amendment", "Repeal", \
"Clarification", "Correction".
- provision_id must exactly match an existing provision_id from the list given to you, UNLESS \
change_type is "New Provision", in which case propose a new provision_id following the same \
naming convention you observe in the existing list (e.g. 'DPDPR-R24' for a new Rule 24).
- confidence_score is a float 0.0-1.0 reflecting how sure you are this is a real, verbatim, \
correctly-matched government change.
- old_full_text should be the current provision's full_text (given to you) when change_type \
is Amendment/Repeal/Clarification/Correction — specifically just the span that actually \
changed, not the whole provision — or null for New Provision.
- new_full_text is the verbatim new clause text from the diff's "+" lines (just the span that \
changed, not the whole provision) — or null for Repeal.
- old_value_summary and new_value_summary are short plain-language one-liners (NOT verbatim \
clause text) describing what changed, for the human-facing view. These are never written back \
over a provision's existing summary — they only ever appear in the change log.
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
    section's reference on a Rules-only fetch (and vice versa).
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


# --------------------------------------------------------------------------
# Diff-first: snapshot storage, hunking, Hindi-dropping, PIB keyword filter
# --------------------------------------------------------------------------

def _normalize_lines(text: str | None) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _get_snapshot(conn, document_id: str) -> dict | None:
    row = conn.execute(
        "SELECT content_hash, content_text FROM source_snapshot WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def _store_snapshot(conn, fetch_result) -> None:
    """
    Only called after a successful classification (changes found or
    legitimately none) — never on failure, so a failed run's retry diffs
    against the same known-good baseline instead of a half-processed one.
    """
    conn.execute(
        "INSERT INTO source_snapshot (document_id, content_hash, content_text, fetched_date) "
        "VALUES (?, ?, ?, date('now')) "
        "ON CONFLICT(document_id) DO UPDATE SET "
        "content_hash = excluded.content_hash, content_text = excluded.content_text, "
        "fetched_date = excluded.fetched_date",
        (fetch_result.document_id, fetch_result.content_hash, fetch_result.content_text),
    )
    conn.commit()


class Hunk:
    __slots__ = ("header", "lines", "changed_lines")

    def __init__(self, header: str):
        self.header = header
        self.lines: list[str] = []          # rendered diff lines, incl. +/-/space prefix
        self.changed_lines: list[str] = []  # just the +/- content, for filtering

    def add(self, prefix: str, content: str):
        self.lines.append(f"{prefix}{content}")
        if prefix in ("+", "-"):
            self.changed_lines.append(content)

    def render(self) -> str:
        return "\n".join([self.header, *self.lines])


def _diff_hunks(old_text: str, new_text: str) -> list[Hunk]:
    """Line-level unified diff, +/-3 lines of context, grouped into hunks."""
    old_lines, new_lines = _normalize_lines(old_text), _normalize_lines(new_text)
    hunks: list[Hunk] = []
    current: Hunk | None = None
    for line in difflib.unified_diff(old_lines, new_lines, n=3, lineterm=""):
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            current = Hunk(line)
            hunks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("+"):
            current.add("+", line[1:])
        elif line.startswith("-"):
            current.add("-", line[1:])
        else:
            current.add(" ", line[1:] if line.startswith(" ") else line)
    return hunks


def _is_mostly_hindi(text: str, threshold: float = HINDI_DROP_THRESHOLD) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    devanagari = sum(1 for c in letters if DEVANAGARI_RE.match(c))
    return (devanagari / len(letters)) > threshold


def _drop_hindi_hunks(hunks: list[Hunk]) -> tuple[list[Hunk], int]:
    """
    Drop mostly-Hindi CHANGED LINES (not whole hunks) — a single hunk can
    legitimately mix an English change with Hindi context or a nearby
    unrelated Hindi change (diff context lines pull nearby changes into
    the same hunk), and dropping the entire hunk in that case would throw
    away a real English change along with the Hindi noise. A hunk that
    ends up with no changed lines left after this is dropped entirely.
    """
    kept, dropped = [], 0
    for h in hunks:
        surviving = [ln for ln in h.lines if not (ln[:1] in ("+", "-") and _is_mostly_hindi(ln[1:]))]
        removed = len(h.lines) - len(surviving)
        if removed:
            dropped += removed
        if any(ln[:1] in ("+", "-") for ln in surviving):
            new_hunk = Hunk(h.header)
            for ln in surviving:
                new_hunk.add(ln[0], ln[1:])
            kept.append(new_hunk)
    return kept, dropped


def _pib_relevant_hunks(hunks: list[Hunk]) -> list[Hunk]:
    """
    PIB's changed passages are new release titles (source content is one
    title per line — see fetch_sources.py's RSS extraction). Keep a hunk
    only if at least one of its ADDED (new) lines looks DPDP-relevant;
    removed lines (old titles falling off the feed's rolling window) are
    never themselves something to report on.
    """
    kept = []
    for h in hunks:
        added = [ln for ln in h.lines if ln.startswith("+")]
        if any(PIB_RELEVANCE_RE.search(ln) for ln in added):
            kept.append(h)
    return kept


def _render_diff(hunks: list[Hunk], max_chars: int = MAX_PROMPT_CHARS) -> str:
    text = "\n\n".join(h.render() for h in hunks)
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    return truncated + f"\n\n[...diff truncated at {max_chars} characters...]"


def _match_provisions_by_number(hunks: list[Hunk], provisions: list[dict]) -> list[dict]:
    """
    Find section/rule numbers mentioned in the changed passages and narrow
    the provisions list to those whose reference contains one of those
    numbers. Falls back to "no full_text sent" (caller's job) rather than
    "no provisions sent" if nothing matches, per Phase 6 spec.
    """
    changed_text = "\n".join(ln for h in hunks for ln in h.changed_lines)
    numbers = {m.group(1) for m in SECTION_OR_RULE_NUM_RE.finditer(changed_text)}
    if not numbers:
        return []
    matched = []
    for p in provisions:
        ref_numbers = set(REFERENCE_LEADING_NUM_RE.findall(p["reference"] or ""))
        if ref_numbers & numbers:
            matched.append(p)
    return matched


def _build_user_prompt(fetch_result, provisions: list[dict], matched: list[dict], diff_text: str) -> str:
    matched_ids = {p["provision_id"] for p in matched}

    def prov_line(p):
        if p["provision_id"] in matched_ids:
            full_text = (p["full_text"] or "")[:2000]
            return (
                f"- {p['provision_id']} ({p['reference']}): {p['current_summary'] or ''}\n"
                f"  full_text: {full_text}"
            )
        return f"- {p['provision_id']} ({p['reference']}): {p['current_summary'] or ''}"

    prov_lines = "\n".join(prov_line(p) for p in provisions)
    return (
        f"SOURCE: {fetch_result.source} — {fetch_result.title}\nURL: {fetch_result.url}\n\n"
        f"=== PROVISIONS ON FILE"
        f"{' (full text shown only for provisions the diff plausibly touches)' if matched_ids else ' (no section/rule number matched in the diff — no full text shown; identify a New Provision from the diff alone if applicable)'} ===\n"
        f"{prov_lines}\n\n"
        f"=== DIFF: CHANGED PASSAGES BETWEEN THE LAST CHECK AND NOW ===\n{diff_text}\n"
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
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=[CHANGES_TOOL],
        tool_choice={"type": "tool", "name": "report_changes"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    if resp.stop_reason == "max_tokens":
        raise ClassificationFailed(
            f"Claude hit max_tokens (stop_reason == 'max_tokens') before finishing its response "
            f"— the diff sent was too large for this reply. Not retried automatically: this is a "
            f"real failure, not a transient one, and needs a human look at why the diff was that big."
        )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "report_changes":
            return block.input
    raise RuntimeError("Claude response had no report_changes tool_use block")


def _normalize_for_match(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _validate(parsed: dict, provisions: list[dict], fetch_result) -> list[dict]:
    known_ids = {p["provision_id"] for p in provisions}
    provisions_by_id = {p["provision_id"]: p for p in provisions}
    changes = parsed.get("changes")
    if not isinstance(changes, list):
        raise ValueError("'changes' is not a list")

    fetched_norm = _normalize_for_match(fetch_result.content_text)

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

        if c["change_type"] in ("Amendment", "Repeal", "Clarification", "Correction"):
            provision = provisions_by_id.get(c["provision_id"])
            current_full_text = _normalize_for_match(provision["full_text"] if provision else "")
            old_norm = _normalize_for_match(c["old_full_text"])
            if old_norm and old_norm not in current_full_text:
                raise ValueError(
                    f"invented text: old_full_text for {c['provision_id']} is not a substring "
                    f"of that provision's current full_text — refusing to trust it."
                )

        if c["new_full_text"]:
            new_norm = _normalize_for_match(c["new_full_text"])
            if new_norm and new_norm not in fetched_norm:
                raise ValueError(
                    f"invented text: new_full_text for {c['provision_id']} is not a substring "
                    f"of the fetched content — refusing to trust it."
                )

        validated.append(c)
    return validated


def classify(fetch_result, conn) -> list[dict]:
    """
    Classify one changed source using the diff-first design: compare
    against the last successfully-classified snapshot (source_snapshot),
    send the model only the changed passages plus the provisions they
    plausibly touch, and validate every returned change against both the
    provision's current text and the fetched content before trusting it.

    Returns a validated list of change dicts — an empty list is a
    legitimate success (no prior snapshot yet = "baseline captured", or a
    real diff that the model correctly found nothing government-caused
    in, or a PIB fetch with no DPDP-relevant new titles). On a genuine
    failure, retries up to MAX_CLASSIFY_ATTEMPTS times; if it still fails,
    marks source_log.processing_status='Error' and raises
    ClassificationFailed (never returns [] for a failure — that would be
    indistinguishable from a genuine "no change" result).
    """
    snapshot = _get_snapshot(conn, fetch_result.document_id)
    if snapshot is None:
        _store_snapshot(conn, fetch_result)
        print(f"[classify_change] {fetch_result.document_id}: no prior snapshot — baseline captured, no AI call.")
        return []

    if snapshot["content_hash"] == fetch_result.content_hash:
        # fetch_all() only returns sources whose hash changed, so this
        # shouldn't normally happen — but if it does, there's nothing to do.
        return []

    hunks = _diff_hunks(snapshot["content_text"], fetch_result.content_text)

    if fetch_result.source == "PIB":
        hunks = _pib_relevant_hunks(hunks)
        if not hunks:
            conn.execute(
                "UPDATE source_log SET processing_status = 'No Change Detected' WHERE document_id = ?",
                (fetch_result.document_id,),
            )
            conn.commit()
            _store_snapshot(conn, fetch_result)
            print(f"[classify_change] {fetch_result.document_id}: no DPDP-relevant PIB titles — No Change Detected, no AI call.")
            return []

    hunks, hindi_dropped = _drop_hindi_hunks(hunks)
    if hindi_dropped:
        print(f"[classify_change] {fetch_result.document_id}: dropped {hindi_dropped} mostly-Hindi changed line(s) (English is authoritative for this tracker).")

    if not hunks:
        conn.execute(
            "UPDATE source_log SET processing_status = 'No Change Detected' WHERE document_id = ?",
            (fetch_result.document_id,),
        )
        conn.commit()
        _store_snapshot(conn, fetch_result)
        print(f"[classify_change] {fetch_result.document_id}: no non-Hindi changed passages left — No Change Detected, no AI call.")
        return []

    provisions = _relevant_provisions(conn, fetch_result)
    matched = _match_provisions_by_number(hunks, provisions)
    diff_text = _render_diff(hunks)
    user_prompt = _build_user_prompt(fetch_result, provisions, matched, diff_text)

    last_error = None
    last_raw = None
    for attempt in range(MAX_CLASSIFY_ATTEMPTS):
        parsed = None
        try:
            parsed = _call_claude(user_prompt)
            validated = _validate(parsed, provisions, fetch_result)
            _store_snapshot(conn, fetch_result)
            return validated
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
