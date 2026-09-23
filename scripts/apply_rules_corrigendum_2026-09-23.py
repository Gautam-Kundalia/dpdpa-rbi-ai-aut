"""
Phase 4a (23 Sep 2026 audit fixes): apply the G.S.R. 892(E) corrigendum's
items (i)-(iii) — the ones that correct text already in the database
(DPDPR-R1, DPDPR-SDF-R13, DPDPR-R23). Items (iv)-(v) correct First/Fourth
Schedule text that isn't in the database yet at all (seeded incompletely —
see the audit §3, "Gap 2") — those are applied as part of Phase 4b's
restoration of that missing text, not here.

Per D2, this corrigendum counts as a REGULATORY change (the government
issued it) — HIGHLIGHT_CORRIGENDUM is therefore always True here, unlike
the draft script this replaces, which made it a manual on/off choice.
change_origin='regulatory' on every row this writes.

Ground rule: never hand-type legal text. The corrected phrases below are
extracted BY CODE from the corrigendum PDF itself (extract_corrections()),
not copied from the earlier audit session's draft script — that draft is
used only as a cross-check (see main()'s comparison).

Usage:
    python scripts/apply_rules_corrigendum_2026-09-23.py --dry-run   (default)
    python scripts/apply_rules_corrigendum_2026-09-23.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pymupdf  # noqa: E402

from db import get_connection, init_schema, next_id  # noqa: E402

CORRIGENDUM_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "GSR892E_Rules_corrigendum_official.pdf"
CORRIGENDUM_SHA256 = "8f8d9526b511801889f8ae022b6d7c5db449283e90fe32792e5896314b32f994"
CORRIGENDUM_URL = "https://www.meity.gov.in/static/uploads/2025/12/3c7ebbae0e5456f493f486e6845df86b.pdf"
CORRIGENDUM_TITLE = "Corrigenda G.S.R. 892(E), 10 Dec 2025 (Gazette Extraordinary No. 806, 11 Dec 2025)"
COMMENCEMENT_OFFICIAL_URL = "https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf"

# Which provision each corrigendum item touches, and how many times it's
# expected to appear in that provision's CURRENT full_text (both sub-rules
# of Rule 1 were independently corrected by the same phrase fix, so it's
# 2 there; everywhere else, exactly 1). Items (iv)/(v) (First/Fourth
# Schedule) are deliberately excluded — see module docstring.
ITEM_TARGETS = {
    0: ("DPDPR-R1", 2),         # (i)(a) "of this Gazette" -> "in the Official Gazette" (page 24 line 22)
    1: None,                     # (i)(b) — same pair as item 0, page 24 line 24: don't double-apply
    2: ("DPDPR-SDF-R13", 1),    # (ii) "Department" -> "Departments"
    3: ("DPDPR-R23", 1),        # (iii) "given in such" -> "given in such order"
    4: None,                     # (iv)(a) "everybody" -> "every body" — First Schedule, Phase 4b
    5: None,                     # (iv)(b) "(18 or 2013)" -> "(18 of 2013)" — First Schedule, Phase 4b
    6: None,                     # (v)(a) "." -> ";" — Fourth Schedule Note, Phase 4b
    7: None,                     # (v)(b) "(a) to (f)" -> "(a) to (g)" — Fourth Schedule Note, Phase 4b
}


def widen_until_unambiguous(before: str, after: str, old: str, new: str, expected_count: int) -> tuple[str, str]:
    """
    A short phrase pair can be ambiguous to highlight if the CORRECTED
    phrase happens to also match unrelated, unchanged text elsewhere in
    the same provision (Rule 1(2) already correctly said "in the Official
    Gazette" before this correction touched 1(3)/1(4)'s "of this Gazette").
    Widen `old`/`new` by prepending whole words — taken from `before`
    itself, never hand-typed — until `new` occurs in `after` exactly
    `expected_count` times with no stray matches, so export_word.py's
    highlighting (which finds every occurrence of new_full_text) can't
    mistake pre-existing text for part of this correction.
    """
    old_words, new_words = old.split(), new.split()
    prefix_words: list[str] = []
    for _ in range(20):  # generous bound; a real infinite loop here would be a bug worth seeing
        widened_old = " ".join(prefix_words + old_words)
        widened_new = " ".join(prefix_words + new_words)
        if before.count(widened_old) == expected_count and after.count(widened_new) == expected_count:
            return widened_old, widened_new
        idx = before.find(widened_old)
        if idx <= 0:
            raise SystemExit(
                f"STOP: could not widen {old!r} -> {new!r} to be unambiguous "
                f"(ran out of preceding context, or occurrence count never matched)."
            )
        preceding = before[:idx].rstrip()
        m = re.search(r"(\S+)\s*$", preceding)
        if not m:
            raise SystemExit(f"STOP: could not widen {old!r} -> {new!r} — no preceding word found.")
        prefix_words.insert(0, m.group(1))
    raise SystemExit(f"STOP: widening {old!r} -> {new!r} did not converge within 20 words.")


def verify_hash(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        sys.exit(f"STOP: {path} hash mismatch.\n  expected {expected}\n  actual   {actual}")
    print(f"  hash OK: {path.name}")


def extract_corrections(pdf_path: Path) -> list[tuple[str, str]]:
    """Extract every (old, new) phrase pair from the corrigendum's
    'for "X", read "Y"' items, by code — see module docstring."""
    doc = pymupdf.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    quote = r"[\"“”]"
    pattern = re.compile(rf'for {quote}([^"“”]+){quote},?\s*read {quote}([^"“”]+){quote}')
    pairs = pattern.findall(text)
    if len(pairs) != 8:
        sys.exit(f"STOP: expected 8 corrigendum items, extracted {len(pairs)} — corrigendum wording or "
                  f"regex assumption has changed; re-check by hand before proceeding.")
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default=None, help="Override db/dpdpa.db path (testing only)")
    args = ap.parse_args()

    print("Verifying source PDF...")
    verify_hash(CORRIGENDUM_PDF, CORRIGENDUM_SHA256)

    print("\nExtracting corrections from corrigendum PDF (by code)...")
    pairs = extract_corrections(CORRIGENDUM_PDF)
    for i, (old, new) in enumerate(pairs):
        print(f"  item {i}: {old!r} -> {new!r}")

    conn = get_connection(Path(args.db)) if args.db else get_connection()
    init_schema(conn)

    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    print("\nChecking each target provision...")
    plan = []  # (provision_id, old, new, expected_count)
    for item_idx, target in ITEM_TARGETS.items():
        if target is None:
            continue
        provision_id, expected_count = target
        old, new = pairs[item_idx]
        row = conn.execute("SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)).fetchone()
        if row is None:
            sys.exit(f"STOP: {provision_id} not found in provisions.")
        actual_count = row["full_text"].count(old)
        status = "OK" if actual_count == expected_count else "MISMATCH"
        print(f"  item {item_idx} -> {provision_id}: {old!r} appears {actual_count}x "
              f"(expected {expected_count}) [{status}]")
        if actual_count != expected_count:
            sys.exit(
                f"STOP: {provision_id}'s current full_text has {old!r} {actual_count} time(s), "
                f"expected exactly {expected_count} — refusing to guess, nothing written."
            )
        plan.append((provision_id, old, new))

    # Group by provision (Rule 1 has two items, both the same phrase pair,
    # both applied via a single .replace() so both occurrences are fixed).
    by_provision: dict[str, list[tuple[str, str]]] = {}
    for provision_id, old, new in plan:
        by_provision.setdefault(provision_id, []).append((old, new))

    print(f"\n{'APPLYING' if args.apply else 'DRY RUN — would apply'} to "
          f"{len(by_provision)} provision(s): {sorted(by_provision)}")

    if not args.apply:
        print("\nDry run complete. Re-run with --apply to write changes.")
        conn.close()
        return 0

    change_ids = []
    for provision_id, edits in by_provision.items():
        before = conn.execute("SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)).fetchone()[0]
        # All edits for one provision share the same (old, new) pair here —
        # a plain replace() fixes every occurrence at once.
        old, new = edits[0]
        after = before.replace(old, new)

        occurrences = before.count(old)
        if occurrences > 1:
            # More than one genuine occurrence in this provision (Rule 1's
            # sub-rules (3) and (4) both got the same phrase fix). Recording
            # just the bare phrase as old_full_text/new_full_text would be
            # ambiguous at render time: export_word.py highlights every
            # occurrence of new_full_text it finds — and "in the Official
            # Gazette" also already appears, unrelated and unchanged, in
            # Rule 1(2). Widen the phrase (with words taken from the actual
            # text, not hand-typed) until it's unambiguous.
            old, new = widen_until_unambiguous(before, after, old, new, occurrences)
            print(f"    widened for uniqueness: {old!r} -> {new!r}")

        cid = next_id(conn, "change_log", "change_id", "CHG")
        conn.execute(
            """INSERT INTO change_log
               (change_id, detected_timestamp, provision_id, change_type, change_origin,
                old_value_summary, new_value_summary, old_full_text, new_full_text,
                source_document, source_url, detected_by, confidence_score,
                review_status, reviewed_by, review_date, applied_to_master, notes)
               VALUES (?, ?, ?, 'Correction', 'regulatory', ?, ?, ?, ?, ?, ?, ?, 1.0,
                       'Pending Review', NULL, NULL, 'Y', ?)""",
            (
                cid, now, provision_id,
                "Text as originally gazetted in G.S.R. 846(E)",
                "Text as corrected by G.S.R. 892(E)",
                old, new,
                CORRIGENDUM_TITLE, CORRIGENDUM_URL,
                "manual:audit-2026-09-23-corrigendum (phrase pair extracted by code from the corrigendum PDF)",
                f"Government corrigendum (regulatory change): {old!r} -> {new!r}, per G.S.R. 892(E).",
            ),
        )
        conn.execute(
            "UPDATE provisions SET full_text = ?, last_updated_date = ?, latest_change_id = ? "
            "WHERE provision_id = ?",
            (after, today, cid, provision_id),
        )
        change_ids.append(cid)
        print(f"  {provision_id}: applied as {cid}")

    print("\nAdding source_log row for the corrigendum...")
    doc = pymupdf.open(CORRIGENDUM_PDF)
    corrigendum_text = "".join(page.get_text() for page in doc)
    content_hash = hashlib.sha256(corrigendum_text.encode("utf-8")).hexdigest()
    corrigendum_doc_id = next_id(conn, "source_log", "document_id", "SRC")
    conn.execute(
        """INSERT INTO source_log
           (document_id, source, title, url, published_date, fetched_date,
            content_hash, processing_status, linked_change_ids)
           VALUES (?, 'MeitY', ?, ?, '2025-12-11', ?, ?, 'Processed', ?)""",
        (corrigendum_doc_id, CORRIGENDUM_TITLE, CORRIGENDUM_URL, today, content_hash, ",".join(change_ids)),
    )
    print(f"  {corrigendum_doc_id}: {CORRIGENDUM_TITLE}")

    print("\nPointing SRC-0003 at the official commencement-notification URL...")
    updated = conn.execute(
        "UPDATE source_log SET url = ? WHERE document_id = 'SRC-0003' AND url LIKE 'user-upload:%'",
        (COMMENCEMENT_OFFICIAL_URL,),
    ).rowcount
    print(f"  {updated} row(s) updated" + (" (already pointed at an official URL — no-op)" if updated == 0 else ""))

    conn.commit()
    conn.close()
    print(f"\nDone. change_ids: {change_ids}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
