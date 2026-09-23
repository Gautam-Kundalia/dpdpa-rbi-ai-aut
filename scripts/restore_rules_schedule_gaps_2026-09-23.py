"""
Phase 4b (23 Sep 2026 audit fixes): restore Rules Schedule text that was
left out when the Rules table was originally seeded. This is a DATA
CORRECTION, not a regulatory change — the government did not touch these
Schedules; the tracker simply never seeded them in full. Every row this
writes gets change_origin='data_correction' and latest_change_id is never
moved, so none of it is ever highlighted as a government amendment.

Ground rule: never hand-type legal text. Every restored word is extracted
by code from docs/audit_2026-09-23/DPDP_Rules_2025_official_2026-09-23.pdf
(SHA-256 verified below) using anchor-string slicing against the library's
own extracted text, with only whitespace/line-join normalisation applied —
never reworded.

Findings from a systematic word-level diff (difflib) of each Schedule's
current DB text against the PDF, done before writing this script:
  - First Schedule (DPDPR-SCH1): missing the Part B Illustration (after
    item 1) and the Note (after item 13). Nothing else differs.
  - Third Schedule (DPDPR-SCH3): row 1's Purpose/Time columns are
    abridged/paraphrased (not just rows 2 and 3, contrary to the initial
    read that flagged only 2 and 3); rows 2 and 3 are placeholder text
    ("Same exceptions as above" / "Same three-year rule as above"); the
    "user" definition (d) collapses the PDF's "(i)/(ii)" structure into a
    single run-on clause.
  - Fourth Schedule (DPDPR-SCH4): missing the Note entirely (7 definitions
    for the healthcare/education exemptions). Tables are already verbatim.
  - Fifth Schedule (DPDPR-SCH5): one real deviation — paragraph 6(2) drops
    "(hereinafter referred to as" before "Leave Rules")". Headings are
    already present and verbatim (contrary to the audit's general claim
    that Fifth/Sixth lost their headings — that turned out not to be true
    for either Schedule by the time this ran; see Sixth Schedule below).
  - Sixth Schedule (DPDPR-SCH6): no content deviations found. Not touched.

Usage:
    python scripts/restore_rules_schedule_gaps_2026-09-23.py --dry-run   (default)
    python scripts/restore_rules_schedule_gaps_2026-09-23.py --apply
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

import pdfplumber  # noqa: E402
import pymupdf  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from db import get_connection, init_schema, next_id  # noqa: E402

RULES_PDF = REPO_ROOT / "docs" / "audit_2026-09-23" / "DPDP_Rules_2025_official_2026-09-23.pdf"
RULES_SHA256 = "eabc7d05e013144615d78ddc0e8b9c9aac1920e814f4fad38ce6560951f5aa08"
ENGLISH_PAGE_RANGE = range(23, 41)  # 0-indexed pages 24-41 (1-indexed)


def normalize(text: str) -> str:
    """For C1/C2 checking only (never for what's actually stored): collapse
    whitespace, curly quotes/dashes to plain, and drop markdown '**' bold
    markers, matching the same normalisation convention as the Act
    verbatim-rebuild's C1 check."""
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[–—]", "-", text)
    text = text.replace("**", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_hash() -> None:
    actual = hashlib.sha256(RULES_PDF.read_bytes()).hexdigest()
    if actual != RULES_SHA256:
        sys.exit(f"STOP: {RULES_PDF} hash mismatch.\n  expected {RULES_SHA256}\n  actual   {actual}")
    print(f"  hash OK: {RULES_PDF.name}")


PAGE_HEADER_LINE_RE = re.compile(
    r"^\s*(\d{1,3}\s*)?(\[?भाग.*|भारत.*|THE GAZETTE OF INDIA.*|\[?PART\s*II.*SEC.*|\d{1,3}\s*)\s*$"
)


def strip_page_headers(page_text: str) -> str:
    """Drop the recurring masthead lines (page number, the Hindi/English
    'THE GAZETTE OF INDIA : EXTRAORDINARY [PART II-SEC. 3(i)]' header) that
    PyMuPDF's plain get_text() otherwise leaves inline with body text at
    every page break -- these would otherwise get woven into a paragraph
    that happens to span two pages."""
    return "\n".join(
        line for line in page_text.split("\n") if not PAGE_HEADER_LINE_RE.match(line)
    )


def pymupdf_english_pages_text() -> list[str]:
    """Per-page, header-stripped text, so anchor slicing can stay within a
    page when needed and paragraphs spanning a page break don't get masthead
    text woven into them."""
    doc = pymupdf.open(RULES_PDF)
    return [strip_page_headers(doc[i].get_text()) for i in ENGLISH_PAGE_RANGE]


def pymupdf_english_text() -> str:
    return "\n".join(pymupdf_english_pages_text())


def pypdf_english_text() -> str:
    reader = PdfReader(RULES_PDF)
    return "\n".join((reader.pages[i].extract_text() or "") for i in ENGLISH_PAGE_RANGE)


def find_anchor(text: str, phrase: str, start: int = 0) -> int:
    """Whitespace-tolerant version of text.index(phrase, start): the PDF
    sometimes wraps a line exactly where `phrase` has a plain space, so a
    literal substring search can miss a real match. Returns the index in
    the ORIGINAL text where the match starts."""
    pattern = re.escape(phrase)
    pattern = re.sub(r"\\ ", r"\\s+", pattern)
    m = re.compile(pattern).search(text, start)
    if not m:
        raise ValueError(f"anchor not found: {phrase!r}")
    return m.start()


def join_paragraph(raw: str) -> str:
    """Collapse a PDF-wrapped block of lines into one paragraph: join lines
    with a space, collapse whitespace runs. Never rewords.

    Exception: a genuine hyphenated compound word ("sub-section", "sub-
    rule") that the PDF happens to line-wrap right after its hyphen (e.g.
    "sub-\\nsection") must rejoin as "sub-section", not "sub- section" —
    the line-wrap position is a PDF layout accident, not a second space in
    the word. Only a hyphen immediately followed by a line break is
    treated this way; a hyphen elsewhere in the text is untouched."""
    raw = re.sub(r"-\n", "-", raw)
    return re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()


def to_db_style(text: str) -> str:
    """The rest of provisions.full_text uses straight quotes for quoted/
    defined terms (confirmed against DPDPR-SCH3's existing, already-verbatim
    Note: '"e-commerce entity"', not typographic quotes) but keeps em/en
    dashes literal (e.g. '**PART A — Conditions...**'). Convert only the
    quote style to match — content and dashes are untouched."""
    return text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')


# --------------------------------------------------------------------------
# First Schedule: Illustration + Note
# --------------------------------------------------------------------------

def extract_first_schedule_illustration() -> str:
    text = pymupdf_english_text()
    # "Illustration." appears more than once in the document (e.g. under
    # Rule 3) -- anchor to the end of First Schedule Part B's item 1 first,
    # so we start searching for "Illustration." only from there.
    item1_end = find_anchor(text, "who maintains such personal data with the consent of that Data Principal.")
    start = text.index("Illustration.", item1_end)
    # End just before item 2's own "2." marker (not at the start of its
    # body text), so that marker isn't swept into the Illustration.
    end = re.search(r"\n\s*2\.\s*\n", text[start:]).start() + start
    raw = text[start:end]
    # raw has: "Illustration.\n<intro paragraph>\n \nCase 1:<...>\n \nCase 2:<...>\n"
    # Each paragraph is preserved exactly as extracted -- including the
    # PDF's own "Case 1:B1" (no space after the colon) -- rather than
    # inserting formatting choices (e.g. bolding "Case N:") that would
    # require guessing at spacing the source doesn't actually have.
    parts = [p for p in raw.split("\n \n") if p.strip()]
    paragraphs = [join_paragraph(p) for p in parts]
    # paragraphs[0] = "Illustration. <intro>" -- split the label from the text
    label, intro = paragraphs[0].split(".", 1)
    paragraphs[0] = intro.strip()
    out = ["**Illustration.**"] + paragraphs
    return to_db_style("\n\n".join(out))


def extract_first_schedule_note() -> str:
    text = pymupdf_english_text()
    start = text.index("Note: In this Schedule")
    end = text.index("SECOND SCHEDULE")
    raw = text[start:end]
    raw = join_paragraph(raw)
    # Apply the already-established corrigendum correction (G.S.R. 892(E)
    # item (iv)(b), applied in Phase 4a to the DB text this Note's item (d)
    # echoes) -- this is not new legal-text authorship, it's the same fix
    # by the same mechanical rule, extracted from the same corrigendum PDF
    # item this script's sibling (apply_rules_corrigendum_2026-09-23.py)
    # already applied and verified.
    before_fix = "(18 or 2013)"
    after_fix = "(18 of 2013)"
    if raw.count(before_fix) != 1:
        sys.exit(f"STOP: expected exactly one {before_fix!r} in the First Schedule Note; found {raw.count(before_fix)}.")
    raw = raw.replace(before_fix, after_fix)
    # Split into the "Note: In this Schedule, —" lead-in and (a)-(d) items.
    lead_in, rest = raw.split("—", 1)
    items = re.split(r"(?=\([a-d]\)\s)", rest.strip())
    items = [i.strip() for i in items if i.strip()]
    out = [f"{lead_in.strip()} —"] + items
    return to_db_style("\n\n".join(out))


# --------------------------------------------------------------------------
# Third Schedule: table (all 3 rows) + "user" definition
# --------------------------------------------------------------------------

def extract_third_schedule_table_cells() -> list[tuple[str, str, str]]:
    """Returns [(class, purpose, time_period), ...] for rows 1-3, word-position
    extracted (pdfplumber) since this is a multi-column table plain text
    extraction interleaves incorrectly."""
    COL1_MAX, COL2_MAX, COL3_MAX = 80, 183, 381
    with pdfplumber.open(RULES_PDF) as pdf:
        all_words = []
        for pi in (34, 35):  # confirmed: Third Schedule table spans PDF pages 35-36
            for w in pdf.pages[pi].extract_words():
                if w["top"] < 50:  # page header
                    continue
                all_words.append({**w, "gtop": pi * 1000 + w["top"]})

    row_markers = sorted(
        (w for w in all_words if w["x0"] < COL1_MAX and re.match(r"^[123]\.$", w["text"])),
        key=lambda w: w["gtop"],
    )[:3]
    note_marker = next(w for w in all_words if w["gtop"] > 35000 and w["text"].startswith("Note"))
    row_bounds = [m["gtop"] for m in row_markers] + [note_marker["gtop"]]

    rows = []
    for i, marker in enumerate(row_markers):
        top_start, top_end = marker["gtop"] - 2, row_bounds[i + 1] - 2
        row_words = [w for w in all_words if top_start <= w["gtop"] < top_end]
        col2 = sorted((w for w in row_words if COL1_MAX <= w["x0"] < COL2_MAX), key=lambda w: (w["gtop"], w["x0"]))
        col3 = sorted((w for w in row_words if COL2_MAX <= w["x0"] < COL3_MAX), key=lambda w: (w["gtop"], w["x0"]))
        col4 = sorted((w for w in row_words if w["x0"] >= COL3_MAX), key=lambda w: (w["gtop"], w["x0"]))

        def cell_text(words):
            return re.sub(r"\s+", " ", " ".join(w["text"] for w in words)).strip()

        rows.append((cell_text(col2), cell_text(col3), cell_text(col4)))
    return rows


def extract_third_schedule_user_definition() -> str:
    text = pymupdf_english_text()
    start = text.index('(d) “user”')
    end = text.index("FOURTH SCHEDULE")
    raw = join_paragraph(text[start:end])
    # raw: (d) "user", in relation to— (i) an e-commerce entity, ... ; and (ii) an online ... information.
    return to_db_style(raw)


# --------------------------------------------------------------------------
# Fourth Schedule: Note (7 items, corrigendum relettering already applied)
# --------------------------------------------------------------------------

def extract_fourth_schedule_note() -> str:
    text = pymupdf_english_text()
    start = text.index("Note: In this Schedule")
    # the SECOND "Note: In this Schedule" occurrence (first is First Schedule's)
    start = text.index("Note: In this Schedule", start + 1)
    end = text.index("FIFTH SCHEDULE")
    raw = join_paragraph(text[start:end])
    lead_in, rest = raw.split("—", 1)

    # The PDF has a duplicate "(a)" (a real printing defect: "advertisement"
    # and "allied healthcare professional" are BOTH labelled (a)) — this is
    # exactly what corrigendum item (v)(b) "(a) to (f)" -> "(a) to (g)"
    # fixes: 7 items should carry 7 distinct letters (a)-(g), and item
    # (v)(a) changes the first item's closing "." to ";" now that it's no
    # longer the section's last-labelled item. Split on the *content*
    # boundary (each definition starts with an opening curly quote after
    # its own label), then reletter and repunctuate programmatically rather
    # than trusting the PDF's own (broken) lettering.
    raw_items = re.split(r"\([a-f]\)\s*(?=“)", rest.strip())
    raw_items = [i.strip() for i in raw_items if i.strip()]
    if len(raw_items) != 7:
        sys.exit(f"STOP: expected 7 Fourth Schedule Note definitions, found {len(raw_items)}.")
    letters = "abcdefg"
    relettered = []
    for idx, item in enumerate(raw_items):
        letter = letters[idx]
        # normalise trailing punctuation: last item keeps '.', others get ';'
        # or '; and' -- preserve whatever conjunction the PDF already used
        # on each item (some end "; and", most end ";"), only fixing the
        # very first item's original terminal "." (corrigendum item v(a)).
        if idx == 0 and item.rstrip().endswith("."):
            item = item.rstrip()[:-1] + ";"
        relettered.append(f"({letter}) {item.strip()}")
    return to_db_style("\n\n".join([f"{lead_in.strip()} —"] + relettered))


# --------------------------------------------------------------------------
# Fifth Schedule: restore "(hereinafter referred to as ...)"
# --------------------------------------------------------------------------

def verify_fifth_schedule_fix(current_full_text: str) -> tuple[str, str]:
    text = pymupdf_english_text()
    start = text.index("FIFTH SCHEDULE")
    end = text.index("SIXTH SCHEDULE")
    pdf_sch5 = text[start:end]
    # Extract the exact phrase from the PDF context, by code, around "Leave Rules"
    m = re.search(r"\(hereinafter referred to as\s*“Leave\s*\nRules”\)", pdf_sch5)
    if not m:
        # fallback: allow the quote/whitespace to vary, still code-extracted
        m = re.search(r"\(hereinafter referred to as[\s\S]{0,10}Leave[\s\S]{0,10}Rules[\s\S]{0,5}\)", pdf_sch5)
    if not m:
        sys.exit("STOP: could not locate the 'hereinafter referred to as \"Leave Rules\"' phrase in the PDF.")
    # Normalise to the DB's own quoting style (straight quotes, as used
    # throughout provisions.full_text elsewhere in this table).
    new_phrase = join_paragraph(m.group(0)).replace("“", '"').replace("”", '"')
    old_phrase = '("Leave Rules")'
    if current_full_text.count(old_phrase) != 1:
        sys.exit(f"STOP: expected exactly one {old_phrase!r} in DPDPR-SCH5's current full_text; "
                  f"found {current_full_text.count(old_phrase)}.")
    return old_phrase, new_phrase


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default=None, help="Override db/dpdpa.db path (testing only)")
    args = ap.parse_args()

    print("Verifying source PDF...")
    verify_hash()

    conn = get_connection(Path(args.db)) if args.db else get_connection()
    init_schema(conn)

    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    def current_text(pid):
        row = conn.execute("SELECT full_text, effective_date, status FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        if row is None:
            sys.exit(f"STOP: {pid} not found in provisions.")
        return row

    changes: dict[str, tuple[str, str]] = {}  # provision_id -> (before, after)

    # --- SCH1 ---
    sch1 = current_text("DPDPR-SCH1")
    before = sch1["full_text"]
    illustration = extract_first_schedule_illustration()
    note1 = extract_first_schedule_note()
    anchor1 = ("1. The Consent Manager shall enable a Data Principal using its platform to give consent "
               "to the processing of her personal data by a Data Fiduciary onboarded onto such platform "
               "either directly to such Data Fiduciary or through another Data Fiduciary onboarded onto "
               "such platform, who maintains such personal data with the consent of that Data Principal.")
    if before.count(anchor1) != 1:
        sys.exit(f"STOP: DPDPR-SCH1 item 1 anchor not found exactly once (found {before.count(anchor1)}).")
    after = before.replace(anchor1, anchor1 + "\n\n" + illustration)
    after = after.rstrip() + "\n\n" + note1
    changes["DPDPR-SCH1"] = (before, after)

    # --- SCH3 ---
    sch3 = current_text("DPDPR-SCH3")
    before = sch3["full_text"]
    table_rows = extract_third_schedule_table_cells()
    user_def = extract_third_schedule_user_definition()
    lines = before.split("\n")
    table_start = next(i for i, l in enumerate(lines) if l.startswith("| Class of Data Fiduciaries"))
    table_end = next(i for i, l in enumerate(lines) if i > table_start and l.strip() == "")
    new_table_lines = [
        "| Class of Data Fiduciaries | Purposes | Time period |",
        "|---|---|---|",
    ]
    for cls, purpose, time_period in table_rows:
        new_table_lines.append(f"| {cls} | {purpose} | {time_period} |")
    new_lines = lines[:table_start] + new_table_lines + lines[table_end:]
    after = "\n".join(new_lines)
    old_d_item = ('(d) "user", in relation to an e-commerce entity, means any person who accesses or avails '
                  'any computer resource of an e-commerce entity; and in relation to an online gaming '
                  'intermediary or a social media intermediary, means any person who accesses or avails of '
                  'any computer resource of an intermediary for the purpose of hosting, publishing, sharing, '
                  'transacting, viewing, displaying, downloading or uploading information.')
    if old_d_item not in after:
        sys.exit("STOP: DPDPR-SCH3's current 'user' definition (d) text not found where expected.")
    after = after.replace(old_d_item, user_def)
    changes["DPDPR-SCH3"] = (before, after)

    # --- SCH4 ---
    sch4 = current_text("DPDPR-SCH4")
    before = sch4["full_text"]
    note4 = extract_fourth_schedule_note()
    after = before.rstrip() + "\n\n" + note4
    changes["DPDPR-SCH4"] = (before, after)

    # --- SCH5 ---
    sch5 = current_text("DPDPR-SCH5")
    before = sch5["full_text"]
    old_phrase, new_phrase = verify_fifth_schedule_fix(before)
    after = before.replace(old_phrase, new_phrase)
    changes["DPDPR-SCH5"] = (before, after)

    # ---- checks ----
    print("\nRunning checks (C1: contiguous substring of PyMuPDF text; C2: cross-check against pypdf)...")
    # The reference texts are the PDF AS CORRECTED BY THE CORRIGENDUM, not
    # the original gazette's uncorrected printing — two of the pieces this
    # script restores (First Schedule Note's "(18 of 2013)", Fourth Schedule
    # Note's relettering/repunctuation) are themselves corrigendum fixes, so
    # checking them against the ORIGINAL uncorrected text would always fail.
    # This mirrors apply_rules_corrigendum_2026-09-23.py, which treats the
    # corrigendum-corrected reading as ground truth once G.S.R. 892(E) is
    # known and already applied.
    def apply_corrigendum(text: str) -> str:
        text = text.replace("(18 or 2013)", "(18 of 2013)")
        return text

    # De-hyphenate PDF line-wraps the same way join_paragraph() does, BEFORE
    # normalize() collapses newlines to spaces (otherwise "sub-\nsection"
    # would become the reference's "sub- section" but the actually-restored
    # text's "sub-section", a spurious mismatch).
    pymupdf_norm = apply_corrigendum(normalize(re.sub(r"-\n", "-", pymupdf_english_text())))
    pypdf_norm = apply_corrigendum(normalize(re.sub(r"-\n", "-", pypdf_english_text())))
    KNOWN_C2_NOISE = ["THE GAZETTE OF INDIA", "EXTRAORDINARY", "PART II", "SEC. 3"]

    failures = []
    # Checks run on just the NEWLY INTRODUCED content (table rows, the user
    # definition, the illustration, the notes) rather than each row's whole
    # full_text — SCH1/SCH4 append, SCH3 replaces a mid-document span, and
    # the untouched surrounding text was already verified verbatim by the
    # original Rules seeding (per the audit's mechanical comparison).
    def check_piece(name, piece, relettered=False):
        """relettered=True: this piece's own item labels ("(a)", "(b)", ...)
        were reassigned by code (Fourth Schedule Note — see
        extract_fourth_schedule_note) to fix the corrigendum's duplicate-(a)
        printing defect, so the labels themselves won't match the PDF's
        original (broken) lettering. Check each item's CONTENT (with its
        own leading label stripped) as a separate contiguous substring,
        rather than the whole relettered blob at once."""
        n = normalize(piece)
        if relettered:
            # Split on the RAW piece's paragraph breaks first -- normalize()
            # collapses "\n\n" to a single space, so splitting the already-
            # normalized text could never find a paragraph boundary.
            items = [normalize(i) for i in piece.split("\n\n") if i.strip()]
            unlabelled = [re.sub(r"^\([a-z]\)\s*", "", i).strip() for i in items]
            missing = []
            for u in unlabelled:
                if not u or u in pymupdf_norm:
                    continue
                # Corrigendum item (v)(a): "." -> ";" for the item that was
                # originally last (see the matching C2 tolerance below).
                if u.endswith(";") and u[:-1] + "." in pymupdf_norm:
                    continue
                missing.append(u)
            if missing:
                failures.append(f"C1 FAILED: {name}: {len(missing)} item(s) not found — e.g. {missing[0][:80]!r}")
            else:
                print(f"  C1 OK: {name} (checked per-item, since item labels were reassigned by code)")
        elif n not in pymupdf_norm:
            failures.append(f"C1 FAILED: {name} not a contiguous substring of the PyMuPDF text.")
        else:
            print(f"  C1 OK: {name}")
        sentences = re.split(r"(?<=[.;])\s+", n)
        for s in sentences:
            s = s.strip()
            if relettered:
                s = re.sub(r"^Note: In this Schedule,?\s*-?\s*", "", s)
                s = re.sub(r"^(and\s+)?\([a-z]\)\s*", "", s)
            if len(s) < 15:
                continue
            if s in pypdf_norm:
                continue
            stripped = s
            for noise in KNOWN_C2_NOISE:
                stripped = stripped.replace(noise, "").strip()
            stripped = normalize(stripped)
            if stripped and stripped in pypdf_norm:
                print(f"  C2 OK (after removing page-header noise): {name} — {s[:60]}...")
                continue
            # Verified, documented exception: PyMuPDF and pypdf sometimes
            # disagree on whether a thin/ambiguous inter-glyph gap in the
            # PDF is a real space (e.g. "Case 1:B1" vs "Case 1: B1") -- both
            # libraries agree on every word, only on this kind of spacing.
            # Confirmed by hand for this specific case before adding this
            # fallback. Collapsing all whitespace (not just runs of it)
            # neutralises exactly that class of disagreement and nothing
            # else, since word identity/order is still required to match.
            if re.sub(r"\s+", "", s) in re.sub(r"\s+", "", pypdf_norm):
                print(f"  C2 OK (after ignoring inter-word spacing, a known PyMuPDF/pypdf extraction "
                      f"disagreement): {name} — {s[:60]}...")
                continue
            # Corrigendum item (v)(a): "." -> ";" for the Fourth Schedule
            # Note's originally-last item, which the relettering makes no
            # longer last. Try the pre-corrigendum trailing punctuation too.
            if relettered and s.endswith(";") and s[:-1] + "." in pypdf_norm:
                print(f"  C2 OK (after trying the pre-corrigendum trailing '.', per corrigendum item (v)(a)): "
                      f"{name} — {s[:60]}...")
                continue
            failures.append(f"C2 FAILED: sentence not found in pypdf text for {name}: {s[:100]!r}")

    check_piece("First Schedule Illustration", illustration)
    check_piece("First Schedule Note", note1)
    check_piece("Third Schedule user definition (d)", user_def)
    check_piece("Fourth Schedule Note", note4, relettered=True)
    for i, (cls, purpose, time_period) in enumerate(table_rows, start=1):
        check_piece(f"Third Schedule row {i} purpose", purpose)
        check_piece(f"Third Schedule row {i} time period", time_period)

    # effective_date/status are re-checked byte-identical right before each
    # row's UPDATE in --apply below (not meaningful to check in --dry-run,
    # since nothing has been written yet).

    if failures:
        print(f"\n{len(failures)} check failure(s):")
        for f in failures:
            print(" ", f)
        print("\nDRY RUN / APPLY ABORTED — nothing written.")
        conn.close()
        return 1

    print(f"\nAll checks passed. {'APPLYING' if args.apply else 'DRY RUN — would apply'} to "
          f"{len(changes)} provision(s): {sorted(changes)}")

    if not args.apply:
        print("\nDry run complete. Re-run with --apply to write changes.")
        conn.close()
        return 0

    change_ids = []
    for pid, (before, after) in changes.items():
        row = conn.execute("SELECT full_text, effective_date, status FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        if row["full_text"] != before:
            sys.exit(f"STOP: {pid}'s full_text changed since the check pass — aborting, nothing written for this row.")
        eff_before, status_before = row["effective_date"], row["status"]

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
                cid, now, pid,
                "Schedule text incompletely seeded (omitted at the original seeding session)",
                "Restored verbatim from the official Rules PDF",
                before, after,
                "DPDP Rules, 2025 (G.S.R. 846(E))",
                "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf",
                "manual:rules-schedule-restoration-2026-09-23 (code-extracted, no model-written text)",
                f"Data-quality fix (not a regulatory change): restored text left out of {pid} at seeding. "
                f"See scripts/restore_rules_schedule_gaps_2026-09-23.py.",
            ),
        )
        conn.execute(
            "UPDATE provisions SET full_text = ?, last_updated_date = ? WHERE provision_id = ?",
            (after, today, pid),
        )
        # never touch latest_change_id -- data_correction rows must never highlight
        after_row = conn.execute("SELECT effective_date, status FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        if (after_row["effective_date"], after_row["status"]) != (eff_before, status_before):
            sys.exit(f"STOP: {pid}'s effective_date/status changed unexpectedly — this should never happen.")
        change_ids.append(cid)
        print(f"  {pid}: applied as {cid}")

    conn.commit()
    conn.close()
    print(f"\nDone. change_ids: {change_ids}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
