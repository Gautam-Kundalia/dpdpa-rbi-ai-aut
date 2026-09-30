"""
One-off repair (30 Sep 2026 audit, findings H-7 and M-11): put back wording
that the Gazette prints and this project's database had dropped.

Two separate things, both in the DPDP Rules 2025:

  H-7  The Seventh Schedule's second row was PARAPHRASED. The Gazette prints
       "...of a Data Principal for the following purposes, namely: — (i)
       performance..."; the database held "...of a Data Principal for: (i)
       performance...". Five words of enacted law were replaced by a colon.
       This is the only real paraphrase the audit found in 545 checked pieces
       of legal text, and it breaks this project's hardest rule.

  M-11 The Fifth and Sixth Schedules each print a separator dash after every
       numbered paragraph heading ("1. Salary. — (1) The Chairperson..."). All
       15 of those dashes were missing from the database.

Both are OUR mistakes, not the government's, so every row written here is
change_origin='data_correction'. That matters: only change_origin='regulatory'
rows are highlighted in the Word documents and reported as a change in the
daily email. A correction to our own typing must not look like a change in the
law — see CLAUDE.md.

Jargon, once:
  - "verbatim" means word-for-word identical to the official Gazette PDF.
  - a "dry run" reads everything, decides everything, prints what it WOULD do,
    and writes nothing. That is what this script does unless you add --apply.

Nothing here is hand-typed. Every restored character is read out of the
official PDF at run time, and the script refuses to write anything if what it
finds there is not exactly what it expects.

Usage:
    python scripts/restore_verbatim_wording_2026-09-30.py            # dry run
    python scripts/restore_verbatim_wording_2026-09-30.py --apply    # writes

Safe to run twice: the second run finds the wording already correct and says
"nothing to do".

Undo: git revert the commit that contains the changed db/dpdpa.db.
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

RULES_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "DPDP_Rules_2025_official_2026-09-23.pdf"
RULES_PDF_SHA256 = "eabc7d05e013144615d78ddc0e8b9c9aac1920e814f4fad38ce6560951f5aa08"
RULES_PDF_URL = "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf"
SOURCE_TITLE = "DPDP Rules 2025, official Gazette PDF (G.S.R. 846(E), 13 Nov 2025)"

# The PDF's English half. Pages 1-23 are the Hindi text; 24-41 are English.
# Same range the project's verbatim test uses.
ENGLISH_PAGES = range(23, 41)

# The paraphrase, and the anchor that makes it findable. `SCH7_OLD` must appear
# exactly once in the stored text or the script stops.
SCH7_OLD = "of a Data Principal for: (i) performance"
# What the Gazette prints in its place is NOT written here — it is read out of
# the PDF by extract_sch7_official_phrase() and checked against this shape.
SCH7_EXPECTED_WORDS = ["for", "the", "following", "purposes", "namely"]

# The 15 numbered paragraph headings, as the database currently stores them.
# `**...**` is Markdown for bold — the project's own presentation, added when
# the Schedules were first typed in; the dash belongs to the enacted text and
# goes after it.
# The trailing `(?!\s*[dashes])` is what makes this script safe to run twice:
# a heading that already carries its dash is simply not matched again. Without
# it a second run cheerfully added a second dash ("1. Salary. — —").
HEADING_RE = re.compile(
    r"(?m)^(\s*(\d+)\.\s+\*\*([^*\n]+?)\.\*\*)(?=\s)(?!\s*[—–-])"
)
HEADING_PROVISIONS = ("DPDPR-SCH5", "DPDPR-SCH6")
EXPECTED_HEADINGS = {"DPDPR-SCH5": 8, "DPDPR-SCH6": 7}


def verify_hash(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        sys.exit(
            f"STOP: {path.name} is not the official copy this script was written against.\n"
            f"  expected sha256 {expected}\n  actual   sha256 {actual}\n"
            f"Nothing was written. Check the file before going further."
        )
    print(f"  hash OK: {path.name}")


def pdf_english_text() -> str:
    doc = pymupdf.open(RULES_PDF)
    return "\n".join(doc[i].get_text() for i in ENGLISH_PAGES)


def extract_sch7_official_phrase(pdf_text: str) -> str:
    """
    Read the Seventh Schedule's real wording out of the PDF (page 41) instead
    of typing it. Returns it on one line, the way the database stores table
    cells.
    """
    m = re.search(
        r"of a Data Principal\s+(for the following\s+purposes,\s+namely:\s*\S)\s*",
        pdf_text,
    )
    if not m:
        sys.exit(
            "STOP: could not find the Seventh Schedule's 'for the following purposes, "
            "namely' wording on the official PDF's English pages. Nothing was written."
        )
    phrase = re.sub(r"\s+", " ", m.group(1)).strip()
    words = re.findall(r"[A-Za-z]+", phrase)
    if words != SCH7_EXPECTED_WORDS:
        sys.exit(f"STOP: the PDF phrase read as {phrase!r}, which is not the expected wording.")
    return phrase


def extract_heading_dash(pdf_text: str, number: str, heading: str) -> str:
    """
    The single dash character the Gazette prints after this numbered heading.
    Read from the PDF so it is never hand-typed — and so that if the Gazette
    ever used something else, this stops rather than inventing one.
    """
    pattern = re.compile(
        rf"(?m)^\s*{re.escape(number)}\.\s*{re.escape(heading)}\.\s*(\S)"
    )
    m = pattern.search(pdf_text)
    if not m:
        sys.exit(
            f"STOP: heading {number}. {heading!r} was not found on the official PDF's "
            f"English pages, so there is nothing to copy its dash from. Nothing was written."
        )
    dash = m.group(1)
    if dash not in "—–-":
        sys.exit(
            f"STOP: the character after heading {number}. {heading!r} in the PDF is {dash!r}, "
            f"which is not a dash. Refusing to guess. Nothing was written."
        )
    return dash


def plan_headings(pdf_text: str, provision_id: str, full_text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Returns (the corrected text, [(before, after), ...] one pair per heading).
    A pure insertion: nothing is deleted or reworded.
    """
    pairs: list[tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        whole, number, heading = m.group(1), m.group(2), m.group(3)
        dash = extract_heading_dash(pdf_text, number, heading)
        # The whitespace that already follows the heading is matched by a
        # lookahead, not consumed, so the result reads exactly as the Gazette
        # prints it: "1. Salary. — (1) The Chairperson...".
        after = f"{whole} {dash}"
        pairs.append((whole.strip(), after.strip()))
        return after

    corrected = HEADING_RE.sub(repl, full_text)
    expected = EXPECTED_HEADINGS[provision_id]
    if not pairs:
        # Every heading already carries its dash: this script has run before.
        # Check that is really why, rather than the headings having vanished.
        found = len(re.findall(r"(?m)^\s*\d+\.\s+\*\*[^*\n]+?\.\*\*", full_text))
        if found != expected:
            sys.exit(
                f"STOP: {provision_id} has no heading left to correct, but {found} numbered "
                f"heading(s) were found where {expected} were expected. The stored text is not "
                f"the shape this script was written for. Nothing was written."
            )
        return full_text, []
    if len(pairs) != expected:
        sys.exit(
            f"STOP: expected {expected} numbered headings in {provision_id}, found {len(pairs)}. "
            f"The stored text is not the shape this script was written for. Nothing was written."
        )
    return corrected, pairs


def record_correction(conn, provision_id, old_span, new_span, now, today, note):
    """Write one data_correction row and point the provision at it."""
    cid = next_id(conn, "change_log", "change_id", "CHG")
    conn.execute(
        """INSERT INTO change_log
           (change_id, detected_timestamp, provision_id, change_type, change_origin,
            old_value_summary, new_value_summary, old_full_text, new_full_text,
            source_document, source_url, detected_by, confidence_score,
            review_status, reviewed_by, review_date, applied_to_master, notes)
           VALUES (?, ?, ?, 'Correction', 'data_correction', ?, ?, ?, ?, ?, ?, ?, 1.0,
                   'Pending Review', NULL, NULL, 'Y', ?)""",
        (
            cid, now, provision_id,
            "Text as this project stored it",
            "Text as the official Gazette prints it",
            old_span, new_span,
            SOURCE_TITLE, RULES_PDF_URL,
            "manual:audit-2026-09-30-verbatim-restore (wording read by code from the official PDF)",
            note,
        ),
    )
    return cid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write the changes (default is a dry run)")
    ap.add_argument("--db", default=None, help="override db/dpdpa.db (testing only)")
    args = ap.parse_args()

    print("Verifying the official Rules PDF...")
    verify_hash(RULES_PDF, RULES_PDF_SHA256)
    pdf_text = pdf_english_text()

    conn = get_connection(Path(args.db)) if args.db else get_connection()
    init_schema(conn)

    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    work: list[tuple[str, str, str, str, str, list[tuple[str, str]]]] = []
    # (provision_id, corrected_full_text, old_span, new_span, note, display pairs)

    # ---------------------------------------------------------------- H-7
    print("\n[H-7] Seventh Schedule (DPDPR-SCH7) — the paraphrase")
    row = conn.execute(
        "SELECT full_text FROM provisions WHERE provision_id = 'DPDPR-SCH7'"
    ).fetchone()
    if row is None:
        sys.exit("STOP: DPDPR-SCH7 not found in provisions. Nothing was written.")
    sch7 = row["full_text"]
    official = extract_sch7_official_phrase(pdf_text)
    sch7_new_span = f"of a Data Principal {official} (i) performance"
    count = sch7.count(SCH7_OLD)
    if count == 0 and sch7.count(sch7_new_span) == 1:
        print("  already correct — nothing to do (this script is safe to run twice).")
    elif count != 1:
        sys.exit(
            f"STOP: expected the paraphrase {SCH7_OLD!r} exactly once in DPDPR-SCH7, "
            f"found it {count} time(s). Refusing to guess. Nothing was written."
        )
    else:
        print("  the two strings, side by side:")
        print(f"    database holds : ...{SCH7_OLD}...")
        print(f"    Gazette prints : ...{sch7_new_span}...")
        print(f"    (the phrase {official!r} was read out of the PDF, page 41)")
        work.append((
            "DPDPR-SCH7", sch7.replace(SCH7_OLD, sch7_new_span),
            SCH7_OLD, sch7_new_span,
            "Our own paraphrase corrected: five words of enacted text "
            f"({official!r}) had been replaced by a colon. Restored verbatim from the "
            "official Rules PDF, page 41. Audit finding H-7.",
            [(SCH7_OLD, sch7_new_span)],
        ))

    # --------------------------------------------------------------- M-11
    for provision_id in HEADING_PROVISIONS:
        label = "Fifth" if provision_id == "DPDPR-SCH5" else "Sixth"
        print(f"\n[M-11] {label} Schedule ({provision_id}) — the heading separator dashes")
        row = conn.execute(
            "SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)
        ).fetchone()
        if row is None:
            sys.exit(f"STOP: {provision_id} not found in provisions. Nothing was written.")
        full_text = row["full_text"]
        corrected, pairs = plan_headings(pdf_text, provision_id, full_text)
        if corrected == full_text:
            print("  already correct — nothing to do.")
            continue
        for before, after in pairs:
            print(f"    before: {before}")
            print(f"    after : {after}")
        # One row per provision: the whole run of headings changed together and
        # they come from one source. old/new spans are the smallest text that
        # contains every insertion, so the audit trail shows exactly what moved.
        start = min(full_text.find(b) for b, _ in pairs)
        end = max(full_text.find(b) + len(b) for b, _ in pairs)
        old_span = full_text[start:end]
        new_span = corrected[start:corrected.find(pairs[-1][1]) + len(pairs[-1][1])]
        work.append((
            provision_id, corrected, old_span, new_span,
            f"Our own omission corrected: the Gazette prints a separator dash after each "
            f"of the {len(pairs)} numbered paragraph headings in the {label} Schedule "
            f"(\"1. Salary. — (1) ...\"); the database dropped them. Pure insertion — no "
            f"word was added, removed or changed. Restored from the official Rules PDF. "
            f"Audit finding M-11.",
            pairs,
        ))

    # ------------------------------------------------------------- summary
    print("\n" + "=" * 70)
    if not work:
        print("Nothing to do: every piece of wording this script repairs is already correct.")
        conn.close()
        return 0

    total_pairs = sum(len(pairs) for *_rest, pairs in work)
    print(f"In plain words: {len(work)} provision(s) would be corrected, covering "
          f"{total_pairs} separate piece(s) of wording.")
    print("Each is recorded as change_origin='data_correction' — our mistake, not a change")
    print("in the law — so none of it is highlighted in the Word documents or reported as")
    print("a government change in the daily email.")
    print("=" * 70)

    if not args.apply:
        print("\nDRY RUN — nothing was written. Re-run with --apply to make these changes.")
        conn.close()
        return 0

    change_ids = []
    for provision_id, corrected, old_span, new_span, note, _pairs in work:
        cid = record_correction(conn, provision_id, old_span, new_span, now, today, note)
        conn.execute(
            "UPDATE provisions SET full_text = ?, last_updated_date = ?, latest_change_id = ? "
            "WHERE provision_id = ?",
            (corrected, today, cid, provision_id),
        )
        change_ids.append(cid)
        print(f"  {provision_id}: corrected, recorded as {cid}")

    conn.commit()

    # Read back rather than trusting the write.
    for provision_id, corrected, *_rest in work:
        stored = conn.execute(
            "SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)
        ).fetchone()["full_text"]
        if stored != corrected:
            sys.exit(f"STOP: {provision_id} did not save as expected. Check the database.")
    print("\nRead back and confirmed: every correction is stored.")

    conn.close()
    print(f"\nDone. New change_log rows: {change_ids}")
    print("Next: python src/export_word.py && python src/export_excel.py, then run the tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
