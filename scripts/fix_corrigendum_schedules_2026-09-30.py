"""
One-off repair (30 Sep 2026 audit, finding H-5): record the last two items of
the government's corrigendum G.S.R. 892(E) as what they actually are — a
change made by the GOVERNMENT — instead of as a correction we made to our own
data.

WHAT WAS WRONG
--------------
G.S.R. 892(E) (10 Dec 2025) makes eight corrections to the DPDP Rules 2025,
grouped into six numbered items. All eight are already correct in this
project's stored text. But only items (i), (ii) and (iii) were recorded as
government changes (CHG-0086, CHG-0087, CHG-0088). Items (iv) and (v) — which
correct the First Schedule and the Fourth Schedule — were swallowed into
CHG-0089 and CHG-0091, two rows marked change_origin='data_correction'
("we fixed our own typing").

Why that matters, in plain words: this project deliberately highlights only
GOVERNMENT changes in the Word documents and only reports those in the daily
email. So two real acts of government were invisible, and the audit trail said
"we fixed our own data" about something the government did. That is the exact
opposite of what change_origin is for.

WHAT THIS SCRIPT DOES
---------------------
Adds FOUR new change_log rows — one per corrected phrase — with
change_origin='regulatory' and change_type='Correction', carrying the same
source document as CHG-0086/87/88. It follows exactly what
scripts/apply_rules_corrigendum_2026-09-23.py did for the first three items.

It does NOT touch provisions.full_text: the text is already correct (the audit
verified all eight substitutions). It does NOT delete or alter CHG-0089 or
CHG-0091 — those stay as the record of our own whole-Schedule restoration. It
does NOT move provisions.latest_change_id: since audit finding H-6 was fixed,
the Word and Excel exports read the change_log directly and no longer depend on
that pointer, so moving it would only make the "most recent thing that happened
to this provision" untrue.

WHAT YOU WILL SEE AFTERWARDS
----------------------------
After running this and regenerating the documents:
  - the Rules Word document gains yellow highlights in the First Schedule
    (two places) and the Fourth Schedule (two places), each with a caption
    naming the corrigendum;
  - the Excel Change_Log sheet gains FOUR new yellow rows.
Nothing else changes.

*** GAUTAM HAS NOT YET APPROVED THIS WORDING. ***
This script prints the four phrase pairs and stays a dry run. Read them, say
yes, and only then run it with --apply.

Jargon, once:
  - a "corrigendum" is an official notice correcting a printing mistake in an
    earlier Gazette notification. It is still an act of government.
  - a "dry run" reads everything, decides everything, prints what it WOULD do,
    and writes nothing.

Nothing here is hand-typed: the phrase pairs are extracted by code from the
corrigendum PDF, and the surrounding context is taken from the stored text
itself.

Usage:
    python scripts/fix_corrigendum_schedules_2026-09-30.py            # dry run
    python scripts/fix_corrigendum_schedules_2026-09-30.py --apply    # writes

Safe to run twice: a second run sees the rows are already there and stops.

Undo: git revert the commit that contains the changed db/dpdpa.db.
"""
from __future__ import annotations

import argparse
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
# Exactly the source_document string CHG-0086/87/88 carry, so the new rows
# group with them under one caption rather than reading as a separate event.
CORRIGENDUM_TITLE = "Corrigenda G.S.R. 892(E), 10 Dec 2025 (Gazette Extraordinary No. 806, 11 Dec 2025)"

RULES_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "DPDP_Rules_2025_official_2026-09-23.pdf"
RULES_PDF_SHA256 = "eabc7d05e013144615d78ddc0e8b9c9aac1920e814f4fad38ce6560951f5aa08"

DETECTED_BY = ("manual:audit-2026-09-30-corrigendum-schedules "
               "(phrase pairs extracted by code from the corrigendum PDF)")

# Which corrigendum item belongs to which provision. Indexes are positions in
# the list extract_corrections() returns, which is the order the corrigendum
# itself prints them.
ITEM_4A, ITEM_4B, ITEM_5A, ITEM_5B = 4, 5, 6, 7


def sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        sys.exit(
            f"STOP: {path.name} is not the official copy this script was written against.\n"
            f"  expected sha256 {expected}\n  actual   sha256 {actual}\nNothing was written."
        )
    print(f"  hash OK: {path.name}")


def extract_corrections(pdf_path: Path) -> list[tuple[str, str]]:
    """Every (old, new) phrase pair from the corrigendum's 'for "X", read "Y"'
    items, read out of the PDF rather than typed. Same routine as the
    23 Sep script, kept independent so neither can quietly change the other."""
    doc = pymupdf.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    quote = r"[\"“”]"
    pattern = re.compile(rf'for {quote}([^"“”]+){quote},?\s*read {quote}([^"“”]+){quote}')
    pairs = pattern.findall(text)
    if len(pairs) != 8:
        sys.exit(
            f"STOP: expected 8 corrigendum items, extracted {len(pairs)}. The corrigendum "
            f"wording or this script's assumption about it has changed. Nothing was written."
        )
    return pairs


def unique_pair(pdf_text: str, stored: str, old: str, new: str, label: str) -> tuple[str, str]:
    """
    The shortest (old, new) pair such that the OLD wording appears exactly once
    in the official pre-corrigendum Rules PDF and the NEW wording appears
    exactly once in today's stored text.

    Why this is needed: apply_change.py and the Word highlighter both require
    "appears exactly once", and "(18 of 2013)" appears THREE times in the First
    Schedule. Only one of them is the one the corrigendum corrected. A pair that
    matched in more than one place would highlight the wrong words.

    The official PDF is the authority for WHICH occurrence — it still prints the
    uncorrected wording, and prints it only once. So any extra context is taken
    from the PDF, never from the corrected text and never by hand. Windows are
    tried shortest-first, and never span a line break, so the same window also
    exists in the stored text (which keeps each clause on one line).
    """
    if pdf_text.count(old) != 1:
        sys.exit(
            f"STOP: item {label}: the official Rules PDF contains {old!r} "
            f"{pdf_text.count(old)} time(s), so this script cannot tell which occurrence "
            f"the corrigendum corrected. Refusing to guess. Nothing was written."
        )
    if stored.count(new) == 1:
        return old, new

    m = re.search(re.escape(old), pdf_text)
    for total in range(1, 160):
        for right in range(total, -1, -1):      # prefer growing to the right
            left = total - right
            lead = pdf_text[max(0, m.start() - left):m.start()]
            tail = pdf_text[m.end():m.end() + right]
            if "\n" in lead or "\n" in tail:
                continue
            ctx_old, ctx_new = lead + old + tail, lead + new + tail
            if pdf_text.count(ctx_old) == 1 and stored.count(ctx_new) == 1:
                return ctx_old, ctx_new
    sys.exit(
        f"STOP: item {label}: could not find a context that is unique in both the official "
        f"PDF and the stored text within 160 characters. Refusing to record an ambiguous "
        f"change. Nothing was written."
    )


def note_item_labels(text: str) -> list[tuple[str, str]]:
    """[(label, first few words of the term), ...] for the Fourth Schedule
    Note's lettered items, in the order they appear."""
    return [(m.group(1), m.group(2))
            for m in re.finditer(r'\(([a-z])\)\s*[\"“]([^\"”]+)[\"”]', text)]


def build_relabelling_pair(full_text: str, rules_pdf_text: str) -> tuple[str, str]:
    """
    Corrigendum item (v)(b) — "lines 1 to 15, for '(a) to (f)', read '(a) to (g)'"
    — is not a phrase swap. The original Gazette printed the Fourth Schedule
    Note's items as (a), (a), (b), (c), (d), (e), (f): two of them were both
    labelled (a). The corrigendum relabels the list (a) to (g).

    So the honest record of what changed is the run of items from the SECOND
    one to the last, with its old letters and its new letters. Both versions are
    derived here — the new one is a literal slice of the stored text, the old
    one is the same slice with each letter put back to what the PDF prints.
    """
    stored = note_item_labels(full_text)
    printed = note_item_labels(rules_pdf_text)
    if len(stored) != 7:
        sys.exit(f"STOP: expected 7 lettered items in the Fourth Schedule Note, found {len(stored)}. "
                 f"Nothing was written.")
    # Find the same seven terms in the PDF, in order, and take their letters.
    terms = [term for _letter, term in stored]
    pdf_letters: list[str] = []
    search_from = 0
    for term in terms:
        for i in range(search_from, len(printed)):
            if printed[i][1].split()[0] == term.split()[0]:
                pdf_letters.append(printed[i][0])
                search_from = i + 1
                break
        else:
            sys.exit(f"STOP: {term!r} was not found in the official PDF's Fourth Schedule Note. "
                     f"Nothing was written.")
    if [l for l, _ in stored] != list("abcdefg"):
        sys.exit(f"STOP: the stored Note items are labelled {[l for l, _ in stored]}, not (a)..(g). "
                 f"Nothing was written.")
    if pdf_letters != list("aabcdef"):
        sys.exit(
            f"STOP: the official PDF's Note items are labelled {pdf_letters}, not the "
            f"(a),(a),(b)..(f) printing defect this script was written for. Nothing was written."
        )

    # The span: from the second item's label to the end of the last item.
    second = re.search(r'\(b\)\s*[\"“]' + re.escape(terms[1].split()[0]), full_text)
    if not second:
        sys.exit("STOP: could not locate the Fourth Schedule Note's second item. Nothing was written.")
    last = re.search(r'\(g\)\s*[\"“]' + re.escape(terms[6].split()[0]), full_text)
    if not last:
        sys.exit("STOP: could not locate the Fourth Schedule Note's last item. Nothing was written.")
    end = full_text.find("\n", last.end())
    end = len(full_text) if end == -1 else end
    new_span = full_text[second.start():end].rstrip()

    old_span = new_span
    for stored_letter, pdf_letter in zip("bcdefg", pdf_letters[1:]):
        old_span = old_span.replace(f"({stored_letter}) “", f"({pdf_letter}) “", 1)
        old_span = old_span.replace(f'({stored_letter}) "', f'({pdf_letter}) "', 1)
    if old_span == new_span:
        sys.exit("STOP: relabelling produced no change. Nothing was written.")
    if full_text.count(new_span) != 1:
        sys.exit("STOP: the Fourth Schedule Note span is not unique. Nothing was written.")
    return old_span, new_span


def already_recorded(conn) -> list[str]:
    rows = conn.execute(
        "SELECT change_id FROM change_log WHERE detected_by = ? ORDER BY change_id",
        (DETECTED_BY,),
    ).fetchall()
    return [r["change_id"] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description="Record corrigendum G.S.R. 892(E) items (iv) and (v) "
                                             "as government changes (audit finding H-5).")
    ap.add_argument("--apply", action="store_true",
                    help="actually write the four rows (default is a dry run)")
    ap.add_argument("--db", default=None, help="override db/dpdpa.db (testing only)")
    args = ap.parse_args()

    print("Verifying the official PDFs...")
    verify_hash(CORRIGENDUM_PDF, CORRIGENDUM_SHA256)
    verify_hash(RULES_PDF, RULES_PDF_SHA256)

    pairs = extract_corrections(CORRIGENDUM_PDF)
    doc = pymupdf.open(RULES_PDF)
    rules_pdf_text = "\n".join(doc[i].get_text() for i in range(23, 41))

    conn = get_connection(Path(args.db)) if args.db else get_connection()
    init_schema(conn)

    existing = already_recorded(conn)
    if existing:
        print(f"\nNothing to do: these four rows are already recorded ({', '.join(existing)}).")
        print("This script is safe to run twice.")
        conn.close()
        return 0

    texts = {}
    for provision_id in ("DPDPR-SCH1", "DPDPR-SCH4"):
        row = conn.execute(
            "SELECT full_text FROM provisions WHERE provision_id = ?", (provision_id,)
        ).fetchone()
        if row is None:
            sys.exit(f"STOP: {provision_id} not found in provisions. Nothing was written.")
        texts[provision_id] = row["full_text"]

    plan: list[tuple[str, str, str, str]] = []  # (provision_id, item label, old, new)

    # -------- item (iv)(a) and (iv)(b): the First Schedule -----------------
    sch1 = texts["DPDPR-SCH1"]
    for idx, label in ((ITEM_4A, "(iv)(a)"), (ITEM_4B, "(iv)(b)")):
        old, new = pairs[idx]
        if sch1.count(new) < 1:
            sys.exit(f"STOP: the corrected wording {new!r} is not in DPDPR-SCH1 at all — the text "
                     f"this script assumes has already changed. Nothing was written.")
        ctx_old, ctx_new = unique_pair(rules_pdf_text, sch1, old, new, label)
        plan.append(("DPDPR-SCH1", label, ctx_old, ctx_new))

    # -------- item (v)(a): the Fourth Schedule Note's full stop ------------
    sch4 = texts["DPDPR-SCH4"]
    old, new = pairs[ITEM_5A]          # "." -> ";"
    # Rebuild the pre-corrigendum Note: the semicolon goes back to a full stop
    # in the one place the corrigendum names (page 38, line 2), which is the end
    # of the Note's first item.
    first_item_end = re.search(r'\(a\)\s*[\"“][^\n]*?(\(\d+ of \d{4}\));', sch4)
    if not first_item_end:
        sys.exit("STOP: could not find the Fourth Schedule Note's first item ending in ';'. "
                 "Nothing was written.")
    anchor_new = first_item_end.group(1) + new       # e.g. "(35 of 2019);"
    anchor_old = first_item_end.group(1) + old       # e.g. "(35 of 2019)."
    # A bare "." is meaningless as a change record, so the Act citation that
    # precedes it — taken from the stored text, and checked against the PDF
    # below — is what makes this item findable.
    ctx_old, ctx_new = unique_pair(rules_pdf_text, sch4, anchor_old, anchor_new, "(v)(a)")
    plan.append(("DPDPR-SCH4", "(v)(a)", ctx_old, ctx_new))

    # -------- item (v)(b): the Fourth Schedule Note's relabelling ----------
    old_span, new_span = build_relabelling_pair(sch4, rules_pdf_text)
    plan.append(("DPDPR-SCH4", "(v)(b)", old_span, new_span))

    # --------------------------------------------------------- show the plan
    print("\n" + "=" * 74)
    print("THE FOUR PHRASE PAIRS — these are what need your approval")
    print("=" * 74)
    for provision_id, label, ctx_old, ctx_new in plan:
        where = "First Schedule" if provision_id == "DPDPR-SCH1" else "Fourth Schedule Note"
        print(f"\n{where} ({provision_id}), corrigendum item {label}")
        if len(ctx_old) > 300:
            print(f"  before (as the Gazette first printed it):\n    {ctx_old[:150]} ...")
            print(f"    ... {ctx_old[-120:]}")
            print(f"  after (as corrected, and as stored today):\n    {ctx_new[:150]} ...")
            print(f"    ... {ctx_new[-120:]}")
        else:
            print(f"  before (as the Gazette first printed it): {ctx_old!r}")
            print(f"  after  (as corrected, and as stored today): {ctx_new!r}")

    print("\n" + "=" * 74)
    print("In plain words: four new rows would be added to the change log, each saying")
    print("'the government corrected this'. No legal text is rewritten — the text is")
    print("already correct. CHG-0089 and CHG-0091 are left exactly as they are.")
    print("\nAfter this and a regenerate, expect EXACTLY this and nothing else:")
    print("  - the Rules Word document: yellow highlights in the First Schedule (2) and")
    print("    the Fourth Schedule (2), each with a caption naming G.S.R. 892(E);")
    print("  - the Excel Change_Log sheet: 4 new yellow rows.")
    print("=" * 74)

    if not args.apply:
        print("\nDRY RUN — nothing was written.")
        print("These pairs have NOT been approved yet. Show them to Gautam, and only")
        print("after he says yes, re-run with --apply.")
        conn.close()
        return 0

    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    change_ids = []
    for provision_id, label, ctx_old, ctx_new in plan:
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
                ctx_old, ctx_new,
                CORRIGENDUM_TITLE, CORRIGENDUM_URL, DETECTED_BY,
                f"Government corrigendum (regulatory change), G.S.R. 892(E) item {label}. "
                f"Recorded on 30 Sep 2026 to correct audit finding H-5: this item was "
                f"previously folded into a change_origin='data_correction' row, so a real "
                f"act of government was never highlighted or reported. "
                f"provisions.full_text is unchanged — it already carries the correction.",
            ),
        )
        change_ids.append(cid)
        print(f"  {provision_id} item {label}: recorded as {cid}")

    conn.commit()
    written = already_recorded(conn)
    if len(written) != 4:
        sys.exit(f"STOP: expected 4 rows after writing, found {len(written)}. Check the database.")
    print(f"\nRead back and confirmed: {', '.join(written)}")
    print(f"\nDone. provisions.full_text was NOT touched (checked: no UPDATE was issued).")
    print("Next: python src/export_word.py && python src/export_excel.py, then run the tests.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
