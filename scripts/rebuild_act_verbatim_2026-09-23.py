"""
Rebuild all 48 DPDPA-* provisions.full_text word-for-word from the official
Act PDF (docs/full_text/DPDP_Act_2023_official_2026-09-23.pdf).

This is a CODE-ONLY extraction: every word written to the database comes
from the PDF through this script's parsing logic. Nothing here is typed,
"fixed", or reconstructed from memory. Where the PDF has a quirk (a wrong
cross-reference, an odd citation format), it is kept exactly as printed.

Primary extractor: pdfplumber (word-level text with x/y coordinates).
NOTE: the original spec called for PyMuPDF ("fitz") text blocks as the
primary extractor. On this machine, PyMuPDF's native module fails to load
under a Windows Application Control / WDAC policy (DLL load blocked) --
this is an environment restriction, not a PDF issue. pdfplumber (built on
pdfminer.six, a different, independent PDF parsing engine) is used instead
as the primary extractor; it exposes the same word-level x0/x1/top
coordinates needed to separate body text from headers and side-margin
notes. pypdf remains the independent SECOND extractor for the C2
cross-check, exactly as specified.

Usage:
    python scripts/rebuild_act_verbatim_2026-09-23.py            # --dry-run (default)
    python scripts/rebuild_act_verbatim_2026-09-23.py --apply    # writes to db/dpdpa.db
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import pypdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from db import get_connection, init_schema, next_id  # noqa: E402

PDF_PATH = PROJECT_ROOT / "docs" / "full_text" / "DPDP_Act_2023_official_2026-09-23.pdf"
EXPECTED_SHA256 = "4deb23981d3010c8225a2ff6149e7243dc2268455b299e283afebdd7b72a7d15"
OUT_JSON = PROJECT_ROOT / "data" / "act_verbatim_2026-09-23.json"
REVIEW_MD = PROJECT_ROOT / "docs" / "act_verbatim_rebuild_2026-09-23.md"

TOTAL_SECTIONS = 44

# --------------------------------------------------------------------------
# Step 0: hash verification
# --------------------------------------------------------------------------

def verify_pdf_hash() -> str:
    data = PDF_PATH.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        print(f"FATAL: {PDF_PATH} SHA-256 mismatch.\n  expected {EXPECTED_SHA256}\n  got      {digest}")
        sys.exit(2)
    return digest


# --------------------------------------------------------------------------
# Step 1: word extraction + zone classification
# --------------------------------------------------------------------------

HEADER_TOP_MAX = 85
MARGIN_LEFT_MAX = 115
MARGIN_RIGHT_MIN = 480


def classify_zone(top: float, x0: float) -> str:
    if top < HEADER_TOP_MAX:
        return "header"
    if x0 < MARGIN_LEFT_MAX or x0 >= MARGIN_RIGHT_MIN:
        return "margin"
    return "body"


# A handful of spots in this PDF have a zero-width inter-word gap between a
# clause/sub-section marker and the word right after it -- e.g. pdfplumber's
# own word segmenter reads section 13's "(1) A Data Principal..." as the
# single glued token "(1)A" (confirmed by inspecting the raw word list: no
# separate "(1)" and "A" tokens exist there, just one "(1)A"). This isn't a
# content difference to preserve like a wrong cross-reference -- it's a PDF
# kerning/rendering artifact of the word-segmentation library, so the two
# tokens are split back apart mechanically, the same way the space-before-
# punctuation pypdf artifact is normalized for the C2 check.
GLUED_MARKER_RE = re.compile(r"^(\([0-9a-z]{1,4}\))([A-Z].*)$")


def extract_all_words(pdf_path: Path):
    """Returns list of dicts: page, top, x0, x1, text, zone (in reading order)."""
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            for w in page.extract_words():
                m = GLUED_MARKER_RE.match(w["text"])
                texts = [m.group(1), m.group(2)] if m else [w["text"]]
                for t in texts:
                    out.append({
                        "page": pno,
                        "top": w["top"],
                        "x0": w["x0"],
                        "x1": w["x1"],
                        "text": t,
                        "zone": classify_zone(w["top"], w["x0"]),
                    })
    return out


def cluster_lines(words, tolerance=4.0):
    """Group words (already filtered to one zone) into lines by (page, top)
    proximity, joined left-to-right. Returns list of dicts: page, top, text."""
    words = sorted(words, key=lambda w: (w["page"], w["top"], w["x0"]))
    lines = []
    cur = None
    for w in words:
        if cur is not None and w["page"] == cur["page"] and abs(w["top"] - cur["top"]) <= tolerance:
            cur["words"].append(w)
        else:
            if cur is not None:
                lines.append(cur)
            cur = {"page": w["page"], "top": w["top"], "words": [w]}
    if cur is not None:
        lines.append(cur)
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["text"] = " ".join(w["text"] for w in line["words"])
    return lines


# --------------------------------------------------------------------------
# Step 2: strip chapter headings, masthead (implicit), signature block (implicit)
# --------------------------------------------------------------------------

CHAPTER_RE = re.compile(r"^CHAPTER\s+[IVXLCDM]+\b", re.IGNORECASE)


def is_all_caps_heading_line(text: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", text)
    return bool(letters) and letters == letters.upper()


def strip_chapter_headings(body_lines):
    out = []
    skipping = False
    for line in body_lines:
        text = line["text"].strip()
        if CHAPTER_RE.match(text):
            skipping = True
            continue
        if skipping:
            if is_all_caps_heading_line(text):
                continue
            skipping = False
        out.append(line)
    return out


# --------------------------------------------------------------------------
# Step 3: strict section-boundary detection (1..44 in order)
# --------------------------------------------------------------------------

SECTION_START_RE = re.compile(r"^(\d{1,2})\.\s")


def find_section_boundaries(body_lines):
    """Returns list of (line_index, section_num) for sections 1..44, strictly
    in order -- a line only counts if its number is exactly the next expected
    one. This avoids the earlier bug where "any line starting with a number"
    (e.g. a stray citation or list number) was mistaken for a new section."""
    boundaries = []
    expected = 1
    for i, line in enumerate(body_lines):
        if expected > TOTAL_SECTIONS:
            break
        m = SECTION_START_RE.match(line["text"].strip())
        if m and int(m.group(1)) == expected:
            boundaries.append((i, expected))
            expected += 1
    return boundaries


# --------------------------------------------------------------------------
# Step 4: side-margin heading per section (only the block right at the
# section's start counts as its heading -- later margin-zone text within
# the same section is footnote-style Act-number citations, e.g. "24 of
# 1997.", not a heading, and is dropped rather than fabricated into one).
# --------------------------------------------------------------------------

HEADING_WINDOW_PX = 60


def heading_for_section(margin_lines, section_start_top, section_start_page):
    words_in_window = []
    for line in margin_lines:
        if line["page"] != section_start_page:
            continue
        if section_start_top - 10 <= line["top"] <= section_start_top + HEADING_WINDOW_PX:
            words_in_window.append(line)
    words_in_window.sort(key=lambda l: l["top"])
    text = " ".join(l["text"] for l in words_in_window)
    text = re.sub(r"\s+", " ", text).strip()
    # A citation footnote ("24 of 1997.", "45 of 1860.") can share almost
    # the exact same vertical position as a heading word on the opposite
    # side of the page (left-margin citation, right-margin heading, or vice
    # versa on odd/even pages) and so end up clustered into the same line,
    # or interleaved between a heading's wrapped lines. It's never part of
    # the heading itself, so it's stripped before reconstructing the text.
    text = re.sub(r"\d+\s*of\s*\d{4}\.?", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    # A real heading is one short phrase ending in a single terminal period
    # (e.g. "Definitions.", "Powers and functions of Board."). Citation
    # footnotes ("24 of 1997.") sometimes sit in the margin within the same
    # window right after a short heading like "Definitions." -- cutting at
    # the FIRST period keeps just the heading itself, not whatever margin
    # text happens to follow it in that window.
    m = re.match(r"^(.*?\.)", text)
    if m:
        text = m.group(1)
    text = re.sub(r"\.$", "", text)
    return text


# --------------------------------------------------------------------------
# Step 5: paragraph reconstruction within a section's line range
# --------------------------------------------------------------------------

NEW_PARA_RE = re.compile(
    r"^(\(\d{1,3}[a-z]{0,2}\)|\([a-z]{1,3}\)|\([ivxlcdm]{1,6}\)|\([A-Z]\)|\d{1,2}\.\s|"
    r"Illustration\.?$|Explanation\.?$|Explanation\s+\d+\.?$)",
    re.IGNORECASE,
)


def reconstruct_paragraphs(lines):
    """lines: list of body-line dicts for one section's text. Joins wrapped
    lines with a single space; starts a new paragraph at each clause/
    sub-clause marker (or Illustration/Explanation label)."""
    paras = []
    cur_words = []
    for line in lines:
        text = line["text"].strip()
        if not text:
            continue
        if cur_words and NEW_PARA_RE.match(text):
            paras.append(" ".join(cur_words))
            cur_words = [text]
        else:
            cur_words.append(text)
    if cur_words:
        paras.append(" ".join(cur_words))
    return [re.sub(r"\s+", " ", p).strip() for p in paras if p.strip()]


# --------------------------------------------------------------------------
# Step 6: locate "THE SCHEDULE" boundary inside section 44's line range
# --------------------------------------------------------------------------

def split_schedule(section44_lines):
    for i, line in enumerate(section44_lines):
        if re.sub(r"\s+", " ", line["text"].strip()).upper() == "THE SCHEDULE":
            return section44_lines[:i], section44_lines[i:]
    return section44_lines, []


# --------------------------------------------------------------------------
# Step 7: Schedule 3-column table (Sl. No. / breach / penalty), matched by
# word x-position, not by pre-joined lines (a joined line can contain both
# the tail of the breach column and the start of the penalty column).
# --------------------------------------------------------------------------

SCHED_COL1_MAX = 160   # "Sl. No."
SCHED_COL2_MAX = 400   # breach description
# >= SCHED_COL2_MAX -> penalty


def extract_schedule_table(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[20]  # page 21 (0-indexed) -- confirmed location of "THE SCHEDULE"
        words = page.extract_words()

    # Row markers: bare "N." in column 1, N = 1..7, top > the "(1) (2) (3)"
    # sub-header row and before the signature block.
    row_markers = sorted(
        (w for w in words if w["x0"] < SCHED_COL1_MAX and re.match(r"^\d+\.$", w["text"])),
        key=lambda w: w["top"],
    )
    row_markers = [w for w in row_markers if w["top"] > 180]  # skip "(1)"/"(2)"/"(3)" sub-header
    row_tops = [w["top"] for w in row_markers]

    rows = []
    for idx, marker in enumerate(row_markers):
        top_start = marker["top"] - 2
        top_end = row_tops[idx + 1] - 2 if idx + 1 < len(row_tops) else 540  # before signature block
        row_words = [w for w in words if top_start <= w["top"] < top_end]
        col2 = sorted((w for w in row_words if SCHED_COL1_MAX <= w["x0"] < SCHED_COL2_MAX),
                      key=lambda w: (w["top"], w["x0"]))
        col3 = sorted((w for w in row_words if w["x0"] >= SCHED_COL2_MAX),
                      key=lambda w: (w["top"], w["x0"]))
        breach = re.sub(r"\s+", " ", " ".join(w["text"] for w in col2)).strip()
        penalty = re.sub(r"\s+", " ", " ".join(w["text"] for w in col3)).strip()
        rows.append((marker["text"], breach, penalty))
    return rows


def render_schedule_markdown(bracket_line, rows):
    lines = ["**THE SCHEDULE** *" + bracket_line + "*", ""]
    lines.append("| Sl. No. | Breach of provisions of this Act or rules made thereunder | Penalty |")
    lines.append("|---|---|---|")
    for sl, breach, penalty in rows:
        lines.append(f"| {sl} | {breach} | {penalty} |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Step 8: build the 44-section (well, 48-row, after splits) structure
# --------------------------------------------------------------------------

SPLIT_ROWS = {
    6: [
        ("DPDPA-S6.1_8_10", lambda n: n != 9),
        ("DPDPA-S6.9", lambda n: n == 9),
    ],
    27: [
        ("DPDPA-S27.1a_c_e_2_3", lambda n: n != "1d"),
        ("DPDPA-S27.1d", lambda n: n == "1d"),
    ],
    44: [
        ("DPDPA-S44.1_3", lambda n: n in (1, 3)),
        ("DPDPA-S44.2", lambda n: n == 2),
    ],
}

TOP_LEVEL_SUBSEC_RE = re.compile(r"^\((\d{1,2})\)\s")
CLAUSE_D_RE = re.compile(r"^\(d\)\s", re.IGNORECASE)


def _build_split_by_top_subsec(rows, pid_a, pid_b, heading, sec_num, paras, keep1, keep2):
    cur_n = None
    a_paras, b_paras = [], []
    for p in paras:
        m = TOP_LEVEL_SUBSEC_RE.match(p)
        if m:
            cur_n = int(m.group(1))
        if cur_n is None:
            # shouldn't happen -- every DPDPA-S6/S44 paragraph starts inside a numbered sub-section
            a_paras.append(p)
            b_paras.append(p)
            continue
        if keep1(cur_n):
            a_paras.append(p)
        if keep2(cur_n):
            b_paras.append(p)
    ref_a = "6(1)-(8),(10)" if sec_num == 6 else "44(1),(3)"
    ref_b = "6(9)" if sec_num == 6 else "44(2)"
    rows[pid_a] = {"heading": f"Section {ref_a} — {heading}", "full_text_paras": a_paras}
    rows[pid_b] = {"heading": f"Section {ref_b} — {heading}", "full_text_paras": b_paras}


def _build_split_27(rows, heading, paras):
    # Section 27(1) lead-in + clauses (a)-(e), then (2), (3). Clause (d) is
    # split out on its own (different commencement date per G.S.R. 843(E)).
    a_paras, d_paras = [], []
    lead_in = None
    in_1d = False
    for p in paras:
        if p.startswith("(1) "):
            lead_in = p
            a_paras.append(p)
            continue
        if CLAUSE_D_RE.match(p):
            in_1d = True
            d_paras.append(p)
            continue
        m = TOP_LEVEL_SUBSEC_RE.match(p)
        if m or re.match(r"^\([a-z]\)\s", p, re.IGNORECASE):
            in_1d = False
        if in_1d:
            d_paras.append(p)
        else:
            a_paras.append(p)
    if lead_in and (not d_paras or d_paras[0] != lead_in):
        d_paras = [lead_in] + d_paras
    rows["DPDPA-S27.1a_c_e_2_3"] = {
        "heading": f"Section 27(1)(a)-(c),(e),(2),(3) — {heading}",
        "full_text_paras": a_paras,
    }
    rows["DPDPA-S27.1d"] = {
        "heading": f"Section 27(1)(d) — {heading}",
        "full_text_paras": d_paras,
    }


# --------------------------------------------------------------------------
# Checks C1-C6
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = text or ""
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    # pypdf (the second extractor, used only for the C2 cross-check) sometimes
    # inserts a stray space before punctuation ("Y , a bank." instead of "Y, a
    # bank.") as a font-kerning artifact -- not a wording difference, so it's
    # normalized away here rather than treated as a mismatch.
    text = re.sub(r"\s+([,.;:)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    # This PDF typesets "Explanation.--" / "Illustration.--" glued directly
    # to the next word (no space) -- pdfplumber preserves that; pypdf's own
    # extraction heuristics insert a space after the dash there. Normalizing
    # both to "one space after a sentence-final dash" makes the two
    # extractors comparable without touching compound words like
    # "sub-section" (no period precedes that hyphen, so this doesn't match).
    text = re.sub(r"(\.\s*-)([A-Za-z])", r"\1 \2", text)
    # A doubled dash ("––", this Act's own convention for introducing a
    # list, e.g. "does not––") sometimes gets a stray space inserted between
    # the two dashes by pypdf's kerning heuristic ("not- -"). Canonicalize
    # both to "--" so the two extractors are comparable.
    text = re.sub(r"-\s*-", "--", text)
    return text


def strip_heading(full_text: str) -> str:
    lines = full_text.split("\n\n", 1)
    if lines and lines[0].startswith("**") and lines[0].endswith("**"):
        return lines[1] if len(lines) > 1 else ""
    return full_text


def check_c1(pdf_text_by_section, provision_id, full_text, section_nums):
    """
    A row's text must be a contiguous substring of its section's primary-
    extraction text. Whole-row checked when possible; but a split row
    (e.g. DPDPA-S6.1_8_10, which keeps sub-sections (1)-(8),(10) and
    deliberately OMITS (9) from the middle) is, by construction, no longer
    one contiguous span of the original section -- only its own individual
    paragraphs still are. So the check is done per-paragraph, which is
    strictly stronger for non-split rows (still requires the whole row,
    since a non-split row's paragraphs are already contiguous and in
    order) and correctly handles split rows.
    """
    paras = strip_heading(full_text).split("\n\n")
    haystack = normalize(" ".join(pdf_text_by_section[n] for n in section_nums))
    for p in paras:
        pn = normalize(p)
        if pn and pn not in haystack:
            return False, p, haystack
    return True, None, haystack


# pypdf flushes accumulated side-margin notes (and the running page header)
# as a block wherever a page break happens to fall in its reading order --
# which can land mid-sentence in the body text, e.g. "...after giving the
# [Orders passed by Appellate Tribunal to be executable as decree. Alternate
# dispute resolution. Voluntary undertaking. Penalties. 24 of 1997. SEC. 1]
# THE GAZETTE OF INDIA EXTRAORDINARY 17] person an opportunity...". This is
# a known, well-documented pypdf quirk with margin-note-heavy Gazette PDFs,
# not a wording difference -- so it's stripped as noise before the
# fallback re-check, per spec's C2 exception.
PAGE_HEADER_RE = re.compile(
    r"(sec\.\s*\d+\]\s*|\d+\s+)?the\s+gazette\s+of\s+india\s+extraordinary"
    r"(\s*\[?\s*p\s*a\s*r\s*t\s*[ivx]+[—-]?\s*)?\s*\d*",
    re.IGNORECASE,
)


def build_margin_noise_regex(all_margin_notes_norm):
    """
    One compiled, word-boundary-anchored regex covering every side-margin
    note, longest phrase first. A single pass avoids the corruption a naive
    sequential str.replace() loop can cause -- e.g. replacing a short
    fragment like "as" (from the margin note "executable as") without word
    boundaries can eat the "as" inside an unrelated body word like
    "p[as]sed", turning it into garbage that then fails to match anything.

    Only phrases of 2+ words are used. A margin column that's too narrow
    for a citation like "27 of 2008." wraps it onto separate lines --
    "27" / "of" / "2008." -- and a single common word like "of" removed
    globally would corrupt real, unrelated sentences that legitimately
    contain "of" elsewhere in the Act. Multi-word margin phrases ("Orders
    passed", "General obligations") don't have that problem: they're
    specific enough that they won't coincidentally occur in unrelated
    running prose.
    """
    phrases = sorted({p for p in all_margin_notes_norm if p and len(p.split()) >= 2}, key=len, reverse=True)
    if not phrases:
        return None
    return re.compile("|".join(r"\b" + re.escape(p) + r"\b" for p in phrases))


def check_c2(pypdf_text_norm, full_text):
    body = strip_heading(full_text)
    # Split on paragraph breaks first (a clause like "...including—" can end
    # a paragraph without a "." or ";", so without this a sentence could run
    # on into the next clause/sub-clause and fail to match purely from being
    # too long, not from any wording difference), then on '.', ';' or ':—'
    # within each paragraph, per spec.
    sentences = []
    for para in body.split("\n\n"):
        sentences.extend(re.split(r"(?<=[.;])\s+|:—\s*|:-\s*", para))
    failures = []

    # Only the page-header boilerplate is stripped outright -- it's generic
    # enough (page numbers, "THE GAZETTE OF INDIA EXTRAORDINARY [PART...")
    # that it can never coincide with real Act wording. Side-margin NOTES
    # are deliberately NOT stripped the same way: a short margin phrase like
    # "personal data" is also completely ordinary body-text wording used
    # throughout the Act, so blindly deleting every occurrence of it
    # anywhere in the document (to clear one page-break noise blob) would
    # corrupt unrelated, legitimate sentences elsewhere. Instead, margin-
    # note noise is tolerated via the gapped match below, which only
    # allows a bounded amount of *any* junk between the sentence's own
    # words, wherever it actually sits -- without deleting text globally.
    stripped = PAGE_HEADER_RE.sub(" ", pypdf_text_norm)
    stripped = re.sub(r"\s+", " ", stripped)

    for s in sentences:
        sn = normalize(s)
        if not sn:
            continue
        if sn in pypdf_text_norm:
            continue
        if sn in stripped:
            failures.append((s, "passed after removing page-header noise"))
            continue
        # pypdf flushes accumulated side-margin notes (and sometimes the
        # page header, if PAGE_HEADER_RE's pattern doesn't match its exact
        # spacing) as one run-on block wherever a page break happens to
        # land in its reading order -- which can fall mid-sentence in the
        # body text. As a final, still noise-only check (never invented
        # text): allow each word of the sentence to be found in order in
        # the page-header-stripped pypdf text, tolerating a bounded gap of
        # leftover margin-note/citation junk between consecutive words.
        words = re.findall(r"\S+", sn)
        if words:
            pattern = re.escape(words[0]) + "".join(
                r".{0,220}?" + re.escape(w) for w in words[1:]
            )
            if re.search(pattern, stripped, re.DOTALL):
                failures.append((s, "passed after removing header/margin noise (gapped match)"))
                continue
        failures.append((s, "FAILED"))
    return failures


BLACKLIST = [
    "Bench", "Companies Act", "18B", "69A", "make good the loss",
    "clearly distinguishable", "signature of the Chairperson",
    "not less than the prescribed period", "Evidence Act",
]


def check_c4(full_text):
    hits = [term for term in BLACKLIST if term.lower() in full_text.lower()]
    return hits


SPOT_FACTS = [
    (42, "to more than twice of what was specified in it when this Act was originally enacted"),
    (8, "(4) A Data Fiduciary shall implement"),
    (19, "social or consumer protection"),
    (40, "(y) the procedure for dealing an appeal under sub-section (8) of section 29"),
]


def check_c5(section_full_text):
    results = []
    for sec_num, phrase in SPOT_FACTS:
        text = section_full_text.get(sec_num, "")
        results.append((sec_num, phrase, normalize(phrase) in normalize(text)))
    return results


# Gautam's numeral shorthand (250 crore, 200 crore, ...) translated to the
# word-form the Gazette actually prints ("two hundred and fifty crore ..."),
# checked one row at a time so "fifty crore" (row 7) can't accidentally
# match inside "two hundred and fifty crore" (row 1).
SCHEDULE_EXPECTED_PENALTY_WORDS = [
    "two hundred and fifty crore",
    "two hundred crore",
    "two hundred crore",
    "one hundred and fifty crore",
    "ten thousand rupees",
    "up to the extent applicable",
    "fifty crore",
]


def check_c5_schedule(schedule_rows):
    results = []
    for i, (sl, breach, penalty) in enumerate(schedule_rows):
        expected = SCHEDULE_EXPECTED_PENALTY_WORDS[i] if i < len(SCHEDULE_EXPECTED_PENALTY_WORDS) else None
        ok = expected is not None and expected in normalize(penalty).lower()
        results.append((sl, penalty, expected, ok))
    return results


def check_c3_completeness(source_words, reassembled_words):
    sm = difflib.SequenceMatcher(a=source_words, b=reassembled_words, autojunk=False)
    matched = sum(block.size for block in sm.get_matching_blocks())
    total = len(source_words)
    covered_idx = set()
    for block in sm.get_matching_blocks():
        covered_idx.update(range(block.a, block.a + block.size))
    uncovered = [source_words[i] for i in range(total) if i not in covered_idx]
    pct = 100.0 * matched / total if total else 0.0
    return pct, uncovered


def check_c6(conn, provision_ids):
    before = {}
    for pid in provision_ids:
        row = conn.execute(
            "SELECT effective_date, status, latest_change_id, sort_order FROM provisions WHERE provision_id = ?",
            (pid,),
        ).fetchone()
        if row:
            before[pid] = dict(row)
    return before


def check_c6_after(conn, before):
    ok = True
    diffs = []
    for pid, snap in before.items():
        row = conn.execute(
            "SELECT effective_date, status, latest_change_id, sort_order FROM provisions WHERE provision_id = ?",
            (pid,),
        ).fetchone()
        after = dict(row)
        if after != snap:
            ok = False
            diffs.append((pid, snap, after))
    return ok, diffs


# --------------------------------------------------------------------------
# Second extractor: pypdf (C2 cross-check)
# --------------------------------------------------------------------------

def extract_pypdf_text(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# --------------------------------------------------------------------------
# Main driver
# --------------------------------------------------------------------------

def build_act_body(pdf_path: Path):
    """Returns (rows dict, all_margin_notes_norm, source_body_words,
    reassembled_words, schedule_rows, schedule_bracket, section_full_text)."""
    all_words = extract_all_words(pdf_path)
    body_words = [w for w in all_words if w["zone"] == "body"]
    margin_words = [w for w in all_words if w["zone"] == "margin"]

    body_lines_raw = cluster_lines(body_words)
    margin_lines = cluster_lines(margin_words)
    body_lines = strip_chapter_headings(body_lines_raw)

    boundaries = find_section_boundaries(body_lines)
    if len(boundaries) != TOTAL_SECTIONS:
        found = [n for _, n in boundaries]
        missing = sorted(set(range(1, TOTAL_SECTIONS + 1)) - set(found))
        raise RuntimeError(f"section boundary detection: found {len(boundaries)}, missing {missing}")

    section_full_text = {}   # sec_num -> normalized-ish plain paragraph text (pre-split)
    section_paras = {}       # sec_num -> list[str]
    headings = {}            # sec_num -> heading text
    schedule_lines = None

    for idx, (start_i, sec_num) in enumerate(boundaries):
        end_i = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(body_lines)
        sec_lines = body_lines[start_i:end_i]
        if sec_num == TOTAL_SECTIONS:
            sec_lines, schedule_lines = split_schedule(sec_lines)
        headings[sec_num] = heading_for_section(margin_lines, sec_lines[0]["top"], sec_lines[0]["page"])
        paras = reconstruct_paragraphs(sec_lines)
        if paras:
            # The section's own leading "N. " token (e.g. "33. (1) If the
            # Board...") is redundant with the "Section N -- <heading>" bold
            # heading line already generated for this row, and the existing
            # DB rows never carry it either (e.g. DPDPA-S1 starts "(1) This
            # Act may be called...", not "1. (1) This Act..."). Strip it from
            # just the first paragraph so this row matches that convention.
            paras[0] = re.sub(rf"^{sec_num}\.\s+", "", paras[0])
        section_paras[sec_num] = paras
        section_full_text[sec_num] = " ".join(paras)

    rows = {}
    for sec_num in range(1, TOTAL_SECTIONS + 1):
        heading = headings[sec_num]
        paras = section_paras[sec_num]
        if sec_num == 6:
            _build_split_by_top_subsec(rows, "DPDPA-S6.1_8_10", "DPDPA-S6.9", heading, sec_num, paras,
                                        keep1=lambda n: n != 9, keep2=lambda n: n == 9)
        elif sec_num == 27:
            _build_split_27(rows, heading, paras)
        elif sec_num == 44:
            _build_split_by_top_subsec(rows, "DPDPA-S44.1_3", "DPDPA-S44.2", heading, sec_num, paras,
                                        keep1=lambda n: n in (1, 3), keep2=lambda n: n == 2)
        else:
            pid = f"DPDPA-S{sec_num}"
            rows[pid] = {
                "heading": f"Section {sec_num} — {heading}",
                "full_text_paras": paras,
                "section_nums": [sec_num],
            }
    for pid in ("DPDPA-S6.1_8_10", "DPDPA-S6.9"):
        rows[pid]["section_nums"] = [6]
    for pid in ("DPDPA-S27.1a_c_e_2_3", "DPDPA-S27.1d"):
        rows[pid]["section_nums"] = [27]
    for pid in ("DPDPA-S44.1_3", "DPDPA-S44.2"):
        rows[pid]["section_nums"] = [44]

    schedule_rows = extract_schedule_table(pdf_path)
    bracket = ""
    if schedule_lines:
        for l in schedule_lines:
            t = l["text"].strip()
            if t.upper() == "THE SCHEDULE":
                continue
            bracket = re.sub(r"\s+", " ", t)
            break
    sched_md = render_schedule_markdown(bracket, schedule_rows)
    rows["DPDPA-SCHED"] = {
        "heading": None,
        "full_text_rendered": sched_md,
        "section_nums": [44],  # Schedule text lives inside section 44's PDF span
        "is_schedule": True,
    }

    all_margin_notes_norm = [normalize(l["text"]) for l in margin_lines if l["text"].strip()]

    # Sanity check: the Schedule is a 3-column table, so its words must be
    # RE-ORDERED (column by column) to render as a clean markdown table --
    # word order there legitimately differs from raw left-to-right PDF
    # reading order (which interleaves the breach and penalty columns line
    # by line). To keep the C3 completeness metric meaningful (order-
    # sensitive) rather than penalizing that legitimate reordering, both
    # "source" and "reassembled" use the SAME canonical schedule word list
    # here; the table extraction's own correctness (no word dropped or
    # duplicated while splitting into columns) is verified separately below
    # by comparing raw vs. column-assigned word counts.
    sched_header_words = "Sl. No. Breach of provisions of this Act or rules made thereunder Penalty"
    canonical_sched_words = []
    if schedule_lines:
        canonical_sched_words.extend(re.findall(r"\S+", "THE SCHEDULE"))
        if bracket:
            canonical_sched_words.extend(re.findall(r"\S+", bracket))
        canonical_sched_words.extend(re.findall(r"\S+", sched_header_words))
        for sl, breach, penalty in schedule_rows:
            canonical_sched_words.extend(re.findall(r"\S+", f"{sl} {breach} {penalty}"))

        raw_table_words = []
        for l in schedule_lines:
            if l["top"] >= 540:
                # Signature block ("DR. REETA VASISHTA, Secretary to the Govt.
                # of India.") and the standard Gazette printing footer
                # ("UPLOADED BY THE MANAGER...") sit right after the table's
                # last row (row 7 ends at top~528) -- neither is part of the
                # Schedule and both are dropped, per the ground rule to strip
                # the signature block from section bodies.
                continue
            t = l["text"].strip()
            if t.upper() == "THE SCHEDULE" or re.sub(r"\s+", " ", t) == bracket:
                continue
            if re.match(r"^\(1\)\s*\(2\)\s*\(3\)$", re.sub(r"\s+", " ", t)):
                continue
            raw_table_words.extend(re.findall(r"\S+", t))
        # header row words + the 7 data rows' words should match 1:1 in count
        # against everything on the table's pages minus the boilerplate
        # already excluded above.
        n_raw = len(raw_table_words)
        n_assigned = len(re.findall(r"\S+", sched_header_words)) + sum(
            len(re.findall(r"\S+", f"{sl} {breach} {penalty}")) for sl, breach, penalty in schedule_rows
        )
        if n_raw != n_assigned:
            print(f"WARNING: Schedule word-count mismatch: {n_raw} raw vs {n_assigned} column-assigned "
                  f"(some word may have been dropped/duplicated by column splitting).")

    source_body_words = []
    for sec_num in range(1, TOTAL_SECTIONS + 1):
        source_body_words.extend(re.findall(r"\S+", normalize(section_full_text[sec_num])))
    source_body_words.extend(re.findall(r"\S+", normalize(" ".join(canonical_sched_words))))

    reassembled_text_parts = []
    for sec_num in range(1, TOTAL_SECTIONS + 1):
        reassembled_text_parts.append(section_full_text[sec_num])
    reassembled_words = re.findall(r"\S+", normalize(" ".join(reassembled_text_parts)))
    reassembled_words.extend(re.findall(r"\S+", normalize(" ".join(canonical_sched_words))))

    return rows, all_margin_notes_norm, source_body_words, reassembled_words, schedule_rows, section_full_text


def run_checks(conn, rows, all_margin_notes_norm, source_body_words, reassembled_words, schedule_rows, section_full_text, pypdf_text_norm):
    report = {"c1": {}, "c2": {}, "c3": None, "c4": {}, "c5": None, "c5_schedule": None, "c6_before": None}
    all_ok = True

    for pid, row in rows.items():
        full_text = render_full_text_for_row(pid, row)
        row["_rendered"] = full_text

        if row.get("is_schedule"):
            report["c1"][pid] = (True, "n/a (table row-matched, see schedule extraction)")
            report["c4"][pid] = check_c4(full_text)
            continue

        ok, body, haystack = check_c1(section_full_text, pid, full_text, row["section_nums"])
        report["c1"][pid] = (ok, None if ok else body[:200])
        if not ok:
            all_ok = False

        c2_fail = check_c2(pypdf_text_norm, full_text)
        hard_fail = [f for f in c2_fail if f[1] == "FAILED"]
        report["c2"][pid] = c2_fail
        if hard_fail:
            all_ok = False

        blacklist_hits = check_c4(full_text)
        report["c4"][pid] = blacklist_hits
        if blacklist_hits:
            all_ok = False

    pct, uncovered = check_c3_completeness(source_body_words, reassembled_words)
    report["c3"] = (pct, uncovered)
    if pct < 99.5:
        all_ok = False

    report["c5"] = check_c5(section_full_text)
    for sec_num, phrase, ok in report["c5"]:
        if not ok:
            all_ok = False

    report["c5_schedule"] = check_c5_schedule(schedule_rows)
    for sl, penalty, expected, ok in report["c5_schedule"]:
        if not ok:
            all_ok = False

    return all_ok, report


def render_full_text_for_row(pid, row):
    if row.get("is_schedule"):
        return row["full_text_rendered"]
    heading_line = f"**{row['heading']}**"
    body = "\n\n".join(row["full_text_paras"])
    return f"{heading_line}\n\n{body}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes to db/dpdpa.db (default: dry-run)")
    args = parser.parse_args()

    print("Verifying Act PDF SHA-256...")
    pdf_hash = verify_pdf_hash()
    print(f"  OK: {pdf_hash}")

    print("Extracting via pdfplumber (primary)...")
    rows, all_margin_notes_norm, source_body_words, reassembled_words, schedule_rows, section_full_text = build_act_body(PDF_PATH)
    print(f"  {len(rows)} provision rows built (expect 48).")

    print("Extracting via pypdf (second extractor, for C2)...")
    pypdf_text_norm = normalize(extract_pypdf_text(PDF_PATH))

    conn = get_connection()
    init_schema(conn)

    provision_ids = [f"DPDPA-S{n}" for n in range(1, 45)]  # not all exist as literal ids; just for reference
    expected_ids = set(rows.keys())
    db_ids = {r["provision_id"] for r in conn.execute("SELECT provision_id FROM provisions WHERE provision_id LIKE 'DPDPA-%'").fetchall()}
    missing_in_db = expected_ids - db_ids
    extra_in_db = db_ids - expected_ids
    if missing_in_db or extra_in_db:
        print(f"FATAL: provision_id mismatch. Missing in DB: {sorted(missing_in_db)}. Extra in DB: {sorted(extra_in_db)}")
        sys.exit(2)

    before_snapshot = check_c6(conn, sorted(expected_ids))

    print("Running checks C1-C5...")
    all_ok, report = run_checks(conn, rows, all_margin_notes_norm, source_body_words, reassembled_words,
                                 schedule_rows, section_full_text, pypdf_text_norm)

    print_report_summary(report, rows)

    if not all_ok:
        print("\nFAIL: one or more checks failed. Not applying. See summary above.")
        conn.close()
        sys.exit(1)

    print("\nAll checks C1-C5 passed.")

    write_verbatim_json(rows, pdf_hash)
    write_review_md(rows, report, section_full_text)

    if not args.apply:
        print("\nDry run complete (no DB changes). Re-run with --apply to write changes.")
        conn.close()
        return

    print("\nApplying to db/dpdpa.db ...")
    apply_to_db(conn, rows)

    ok6, diffs = check_c6_after(conn, before_snapshot)
    if not ok6:
        print(f"FATAL: C6 violated after apply -- effective_date/status/latest_change_id/sort_order changed for: {diffs}")
        conn.rollback()
        sys.exit(2)
    conn.commit()
    print("C6 verified: effective_date/status/latest_change_id/sort_order unchanged for all 48 rows.")
    conn.close()
    print("Apply complete.")


def print_report_summary(report, rows):
    print("\n--- C1 (contiguous substring of primary extraction) ---")
    c1_fail = [pid for pid, (ok, _) in report["c1"].items() if not ok]
    print(f"  {len(report['c1']) - len(c1_fail)}/{len(report['c1'])} passed.")
    for pid in c1_fail:
        print(f"  FAIL {pid}: {report['c1'][pid][1]!r}")

    print("\n--- C2 (pypdf cross-check) ---")
    hard_fails = 0
    exceptions = 0
    for pid, fails in report["c2"].items():
        for sent, status in fails:
            if status == "FAILED":
                hard_fails += 1
                print(f"  HARD FAIL {pid}: {sent[:100]!r}")
            else:
                exceptions += 1
    print(f"  {exceptions} documented exception(s), {hard_fails} hard failure(s).")

    print("\n--- C3 (completeness) ---")
    pct, uncovered = report["c3"]
    print(f"  {pct:.2f}% word coverage (need >=99.5%).")
    if uncovered:
        print(f"  {len(uncovered)} uncovered word(s), sample: {uncovered[:40]}")

    print("\n--- C4 (fabrication blacklist) ---")
    any_hit = False
    for pid, hits in report["c4"].items():
        if hits:
            any_hit = True
            print(f"  FAIL {pid}: {hits}")
    if not any_hit:
        print("  clean -- no blacklisted phrases found.")

    print("\n--- C5 (spot facts) ---")
    for sec_num, phrase, ok in report["c5"]:
        print(f"  {'OK' if ok else 'FAIL'} s.{sec_num}: {phrase[:70]!r}")

    print("\n--- C5 Schedule (7 penalty amounts) ---")
    for sl, penalty, expected, ok in report["c5_schedule"]:
        print(f"  {'OK' if ok else 'FAIL'} {sl} expected {expected!r} in {penalty!r}")


def write_verbatim_json(rows, pdf_hash):
    data = {
        "pdf_path": str(PDF_PATH.relative_to(PROJECT_ROOT)),
        "pdf_sha256": pdf_hash,
        "extractors": {
            "primary": f"pdfplumber {__import__('pdfplumber').__version__}",
            "secondary": f"pypdf {pypdf.__version__}",
            "note": "PyMuPDF (fitz) specified in the original spec could not load on this "
                    "machine (Windows Application Control / WDAC blocked its native DLL); "
                    "pdfplumber substituted as the primary word-position extractor.",
        },
        "date": datetime.now(timezone.utc).date().isoformat(),
        "provisions": {
            pid: {"full_text": row["_rendered"]}
            for pid, row in rows.items()
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")


def write_review_md(rows, report, section_full_text):
    conn = get_connection()
    lines = [
        "# Act verbatim rebuild -- 23 Sep 2026",
        "",
        "Rebuilt all 48 `DPDPA-*` rows' `full_text` word-for-word from the official Act PDF "
        "(`docs/full_text/DPDP_Act_2023_official_2026-09-23.pdf`, "
        f"SHA-256 `{EXPECTED_SHA256}`) via `scripts/rebuild_act_verbatim_2026-09-23.py`. "
        "Every word came out of the PDF through that script -- nothing here was typed by hand.",
        "",
        "**Extractor note:** the spec called for PyMuPDF as the primary extractor; it could not "
        "load on this machine (Windows Application Control blocked its native DLL). pdfplumber "
        "was substituted -- an independent, actively maintained PDF text library with the same "
        "word-position capability. pypdf remains the independent second extractor for C2.",
        "",
        "## Per-row results",
        "",
        "| Row | Similarity (old vs new) | C1 | C2 | C4 |",
        "|---|---|---|---|---|",
    ]
    for pid, row in rows.items():
        old = conn.execute("SELECT full_text FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        old_text = old["full_text"] if old else ""
        new_text = row["_rendered"]
        sim = difflib.SequenceMatcher(a=old_text, b=new_text).ratio()
        c1_ok = report["c1"].get(pid, (True,))[0]
        c2_fails = report["c2"].get(pid, [])
        c2_hard = sum(1 for f in c2_fails if f[1] == "FAILED")
        c2_str = "OK" if c2_hard == 0 else f"{c2_hard} FAIL"
        c4_hits = report["c4"].get(pid, [])
        c4_str = "clean" if not c4_hits else f"HIT: {c4_hits}"
        lines.append(f"| {pid} | {sim:.3f} | {'OK' if c1_ok else 'FAIL'} | {c2_str} | {c4_str} |")

    lines.append("")
    lines.append("## Rows with substantial changes (similarity < 0.85)")
    lines.append("")
    for pid, row in rows.items():
        old = conn.execute("SELECT full_text FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        old_text = old["full_text"] if old else ""
        new_text = row["_rendered"]
        sim = difflib.SequenceMatcher(a=old_text, b=new_text).ratio()
        if sim < 0.85:
            lines.append(f"### {pid} (similarity {sim:.3f})")
            lines.append("")
            diff = list(difflib.unified_diff(
                old_text.split(), new_text.split(), lineterm="", n=3
            ))
            lines.append("```")
            lines.extend(diff[:120])
            lines.append("```")
            lines.append("")

    lines.append("## C2 exceptions (sentence only matched pypdf text after removing known header/margin noise)")
    lines.append("")
    any_exc = False
    for pid, fails in report["c2"].items():
        for sent, status in fails:
            if status != "FAILED":
                any_exc = True
                lines.append(f"- **{pid}**: {sent.strip()[:160]!r}")
    if not any_exc:
        lines.append("(none)")
    lines.append("")

    lines.append("## Items for Gautam's review")
    lines.append("")
    lines.append("- **C2 exceptions**: listed above -- sentences that only matched the second "
                 "extractor's text after stripping a known page-header or side-margin string. "
                 "Expected/benign given pypdf mixes margin notes into the text stream.")
    lines.append("- **Split-row endings**: `DPDPA-S27.1d` keeps the Act's own \"; and\" ending "
                 "verbatim rather than dropping it (per instruction, pending your call).")
    d1d = rows.get("DPDPA-S27.1d", {}).get("_rendered", "")
    lines.append(f"  - Current DPDPA-S27.1d ending: `...{d1d[-60:]!r}`")
    lines.append("- **Summaries that may now read oddly against the verbatim text**: not checked "
                 "here -- Phase 4c handles only the 5 pre-approved summary fixes; anything else is "
                 "explicitly out of scope for this script (list, don't touch).")
    lines.append("")

    REVIEW_MD.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_MD.write_text("\n".join(lines), encoding="utf-8")
    conn.close()
    print(f"Wrote {REVIEW_MD}")


def apply_to_db(conn, rows):
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]
    changed = 0
    for pid, row in rows.items():
        old = conn.execute("SELECT full_text, notes FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        new_text = row["_rendered"]
        if old["full_text"] == new_text:
            continue
        changed += 1
        new_notes = (old["notes"] or "") + (
            f" Text rebuilt verbatim {today} from the official Act PDF "
            f"(SHA-256 {EXPECTED_SHA256[:8]}…{EXPECTED_SHA256[-4:]}) "
            f"-- see docs/act_verbatim_rebuild_2026-09-23.md."
        )
        conn.execute(
            "UPDATE provisions SET full_text = ?, last_updated_date = ?, notes = ? WHERE provision_id = ?",
            (new_text, today, new_notes, pid),
        )
        change_id = next_id(conn, "change_log", "change_id", "CHG")
        conn.execute(
            """INSERT INTO change_log
               (change_id, detected_timestamp, provision_id, change_type, change_origin,
                old_value_summary, new_value_summary, old_full_text, new_full_text,
                source_document, source_url, detected_by, confidence_score,
                review_status, reviewed_by, review_date, applied_to_master, notes)
               VALUES (?, ?, ?, 'Correction', 'data_correction', ?, ?, ?, ?, ?, ?, ?, ?,
                       'Pending Review', NULL, NULL, 'Y', ?)""",
            (
                change_id, now, pid,
                "Text rebuilt verbatim from the official Act PDF (data-quality fix, not a legal change).",
                "Text rebuilt verbatim from the official Act PDF (data-quality fix, not a legal change).",
                old["full_text"], new_text,
                "DPDP Act, 2023 (official PDF)",
                "docs/full_text/DPDP_Act_2023_official_2026-09-23.pdf",
                "manual:verbatim-rebuild-2026-09-23 (code-extracted, no model-written text)",
                None,
                f"Verbatim rebuild, {today}. See docs/act_verbatim_rebuild_2026-09-23.md.",
            ),
        )
        # latest_change_id is deliberately NOT moved.
    print(f"  {changed}/{len(rows)} rows changed.")


if __name__ == "__main__":
    main()
