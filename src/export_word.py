"""
Generate DPDP_Rules_2025.docx and DPDP_Act_2023.docx from db/dpdpa.db.

Layout mirrors the actual Gazette structure: each provision is a heading
(bookmarked, for linking from Excel) followed by its verbatim clause text.
A manual, clickable table of contents sits at the top of each document.

Amendment convention: a provision is shown as amended only if
provisions.latest_change_id points at an applied change_log row with
change_origin='regulatory' and change_type != 'New Provision' — i.e. only
a change the government actually made. Our own data corrections (typos,
paraphrase fixes, restored omissions — change_origin='data_correction')
are never highlighted; they stay in change_log as an audit trail only.

Within a regulatory change, only the WORDS THAT CHANGED are highlighted,
not the whole provision: old_full_text and new_full_text are compared
word by word (see word_diff_segments below); inserted/replaced words get
a yellow highlight, removed words get a grey strikethrough shown inline
immediately before the text that replaced them. A small grey caption
("Amended by <source>, <change_id>, <date>") is added under the text.

Usage:
    python src/export_word.py
"""
from __future__ import annotations

import re
import sys

from datetime import date

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from db import PROJECT_ROOT, get_connection
from word_diff import diff_words

# Audit finding L-8: these documents may be read by, or quoted to, a client, so
# each one has to carry its own provenance — where the text came from, how
# current it is, and that it is not legal advice. Before 30 Sep 2026 a reader
# could not tell from the file itself when it was made or what it was based on.
DISCLAIMER = (
    "This is a reading copy generated from the project database. It is not legal "
    "advice. Verify any clause you quote against the official Gazette."
)

DOCX_SPECS = [
    {
        "path": "docs/DPDP_Rules_2025.docx",
        "title": "The Digital Personal Data Protection Rules, 2025",
        "subtitle": "Consolidated text, generated from db/dpdpa.db — Source: Gazette Notification "
                     "G.S.R. 846(E), dated 13 November 2025",
        "provenance": [
            "Incorporates Corrigendum G.S.R. 892(E) dated 10 December 2025 "
            "(Gazette Extraordinary No. 806, 11 December 2025).",
        ],
    },
    {
        "path": "docs/DPDP_Act_2023.docx",
        "title": "The Digital Personal Data Protection Act, 2023",
        "subtitle": "Consolidated text, generated from db/dpdpa.db — Source: Act No. 22 of 2023, "
                     "as notified in phases per G.S.R. 843(E), dated 13 November 2025",
        "provenance": [],
    },
]

HEADING_COLOR = RGBColor(0x1F, 0x38, 0x64)
GREY = RGBColor(0x59, 0x59, 0x59)


# --------------------------------------------------------------------------
# Low-level helpers: bookmarks and internal hyperlinks (python-docx has no
# built-in API for either, so these drop down to raw OXML).
# --------------------------------------------------------------------------

def add_bookmark(paragraph, name, bookmark_id):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def add_internal_hyperlink(paragraph, text, anchor):
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rpr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)
    run.append(rpr)

    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


# --------------------------------------------------------------------------
# Markdown-lite rendering: **bold**, blank-line paragraphs, '|' tables
# --------------------------------------------------------------------------

def add_inline_runs(paragraph, text, highlight=False, strike=False):
    parts = re.split(r"(\*\*.*?\*\*|\*.*?\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 1:
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        if highlight:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if strike:
            run.font.strike = True
            run.font.color.rgb = GREY


def is_table_block(block: str) -> bool:
    first_line = block.strip().split("\n")[0]
    return first_line.strip().startswith("|")


def add_markdown_table(doc, block: str):
    lines = [l for l in block.split("\n") if l.strip()]
    rows = []
    for line in lines:
        if re.match(r"^\s*\|?\s*-+\s*(\|\s*-+\s*)*\|?\s*$", line):
            continue  # separator row
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    table.style = "Table Grid"
    for r_idx, row in enumerate(rows):
        for c_idx in range(ncols):
            cell_text = row[c_idx] if c_idx < len(row) else ""
            cell = table.cell(r_idx, c_idx)
            cell.text = ""
            p = cell.paragraphs[0]
            add_inline_runs(p, cell_text)
            if r_idx == 0:
                for run in p.runs:
                    run.bold = True
    doc.add_paragraph()


def render_markdown_body(doc, text: str, highlight=False, strike=False):
    if not text:
        return
    blocks = text.split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        if is_table_block(block):
            add_markdown_table(doc, block)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            lines = block.split("\n")
            for i, line in enumerate(lines):
                if i > 0:
                    p.add_run().add_break()
                add_inline_runs(p, line, highlight=highlight, strike=strike)


# --------------------------------------------------------------------------
# Word-level diff: highlight only the words that changed (D1/D2)
# diff_words() lives in word_diff.py, shared with notify.py's email
# snippets, so the docx highlighting and the email always agree.
# --------------------------------------------------------------------------

def split_blocks_with_offsets(text):
    """Same paragraph split as render_markdown_body (on '\\n\\n'), but keeping
    each block's (start, end) character offset within the original text."""
    blocks = []
    offset = 0
    for part in text.split("\n\n"):
        start = offset
        end = start + len(part)
        blocks.append((start, end, part))
        offset = end + 2
    return blocks


def _find_all_spans(text, sub):
    """All non-overlapping (start, end) occurrences of `sub` in `text`."""
    spans = []
    start = 0
    while True:
        idx = text.find(sub, start)
        if idx == -1:
            break
        spans.append((idx, idx + len(sub)))
        start = idx + len(sub)
    return spans


def _add_diff_words(paragraph, old_words, new_words):
    for words, style in diff_words(old_words, new_words):
        text = " ".join(words)
        if not text:
            continue
        run = paragraph.add_run(text)
        if style == "delete":
            run.font.strike = True
            run.font.color.rgb = GREY
        elif style == "insert":
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        paragraph.add_run(" ")


def render_block_with_diff(paragraph, block_text, spans):
    """
    Render one markdown-lite block into `paragraph` as a single docx
    paragraph, applying word-diff highlighting at every span in `spans`.

    `spans` is a list of (start, end, old_words, new_words) — character
    offsets within block_text plus the word lists for THAT span's own
    change. Two things make this list rather than a single span:

    - one corrigendum item can correct the same phrase more than once
      inside one provision (Rule 1(3) and 1(4) both had "of this Gazette"
      corrected), so every occurrence must be highlighted, not just the first;
    - a provision can have been amended MORE THAN ONCE over time, and each
      amendment highlights its own words (audit finding M-1). Before
      30 Sep 2026 only the most recent change was ever shown.
    """
    pos = 0
    for start, end, old_words, new_words in spans:
        prefix = block_text[pos:start]
        if prefix:
            add_inline_runs(paragraph, prefix)
        _add_diff_words(paragraph, old_words, new_words)
        pos = end
    suffix = block_text[pos:]
    if suffix:
        add_inline_runs(paragraph, suffix)


def add_amendment_caption(doc, amendments):
    """
    One caption line per amendment, newest first. Several amendments from the
    same source document on the same day are grouped onto one line, so a
    corrigendum that corrected four separate phrases reads as one event rather
    than four (audit finding M-1).
    """
    if not isinstance(amendments, (list, tuple)):
        amendments = [amendments]
    grouped: list[tuple[str, str, list[str]]] = []
    for amendment in amendments:
        source = amendment["source_document"] or "official source"
        date = (amendment["detected_timestamp"] or "")[:10]
        if grouped and grouped[-1][0] == source and grouped[-1][1] == date:
            grouped[-1][2].append(amendment["change_id"])
        else:
            grouped.append((source, date, [amendment["change_id"]]))

    for source, date, change_ids in grouped:
        p = doc.add_paragraph()
        run = p.add_run(f"Amended by {source} ({', '.join(change_ids)}, {date})")
        run.font.size = Pt(8.5)
        run.font.color.rgb = GREY
        run.italic = True


def render_provision_body(doc, full_text, amendments):
    """
    Render a provision's body text, highlighting the changed words of EVERY
    applied regulatory change to it (`change_origin='regulatory'`), newest
    first, and adding a caption naming each one.

    Two audit findings shaped this:

    - **M-1** — only the most recent change used to be shown, so a provision
      amended twice lost the first amendment's highlighting entirely.
    - **H-6** — the amendment to show was found by following
      `provisions.latest_change_id` and *then* requiring
      `change_origin='regulatory'`. A data correction applied after a real
      amendment moved `latest_change_id`, the filter rejected it, and the
      earlier amendment's highlighting, caption and Excel cell all silently
      vanished. The README claimed data corrections "never affect rendering";
      they erased an earlier amendment's rendering. The fix is to ask
      `change_log` for the newest QUALIFYING changes instead — see
      fetch_amendments.

    Each change is highlighted at EVERY occurrence of its `new_full_text`,
    since one corrigendum item can correct the same phrase more than once
    inside a single provision (Rule 1(3) and 1(4) both had "of this Gazette"
    corrected).

    Returns True if a warning was logged — a change whose `new_full_text` is
    no longer in the current text (a later correction moved it, say) is still
    captioned, just not highlighted. It never mis-highlights.
    """
    full_text = full_text or ""
    if amendments is None:
        amendments = []
    elif not isinstance(amendments, (list, tuple)):
        amendments = [amendments]
    amendments = [a for a in amendments if a["new_full_text"]]

    if not amendments:
        render_markdown_body(doc, full_text)
        return False

    blocks = split_blocks_with_offsets(full_text)
    # (block offsets) -> list of (span_start, span_end, old_words, new_words)
    diff_blocks: dict[tuple[int, int], list] = {}
    warned = False
    claimed: dict[tuple[int, int], list[tuple[int, int]]] = {}

    for amendment in amendments:
        new_full_text = amendment["new_full_text"]
        old_words = re.findall(r"\S+", amendment["old_full_text"] or "")
        new_words = re.findall(r"\S+", new_full_text)
        placed = 0
        for start, end, block in blocks:
            if is_table_block(block) or new_full_text not in block:
                continue
            for span_start, span_end in _find_all_spans(block, new_full_text):
                # Two amendments can name overlapping text (a later one
                # rewrote part of what an earlier one changed). Highlighting
                # both would produce nonsense, so the newer one wins and the
                # older is captioned only.
                if any(span_start < c_end and c_start < span_end
                       for c_start, c_end in claimed.get((start, end), [])):
                    continue
                diff_blocks.setdefault((start, end), []).append(
                    (span_start, span_end, old_words, new_words)
                )
                claimed.setdefault((start, end), []).append((span_start, span_end))
                placed += 1
        if placed == 0:
            # Two very different reasons a change cannot be highlighted, and
            # only one of them is a problem.
            #
            # If the changed words are STILL THERE in the provision's text,
            # nothing is wrong: they just don't sit inside one paragraph, or
            # they sit inside a table. A government change can legitimately
            # span several paragraphs — corrigendum G.S.R. 892(E) item (v)(b)
            # relabels a whole run of the Fourth Schedule Note's items — and
            # this renderer only ever highlights text it can find whole inside
            # a single block, deliberately, so it can never highlight the wrong
            # words. That case is captioned and reported as a NOTE, because
            # making it a warning would print the same alarming line on every
            # regenerate forever, and a warning nobody can act on is how the
            # one that matters gets missed (audit finding M-3).
            #
            # If the changed words are GONE from the text, that IS a problem
            # worth a human's attention: a later correction moved them, or the
            # recorded change no longer matches reality.
            still_present = new_full_text in full_text
            if still_present:
                print(
                    f"NOTE: {amendment['change_id']}'s changed text spans more than one "
                    f"paragraph (or sits inside a table), so it is captioned rather than "
                    f"highlighted. The text itself is present and correct.",
                    file=sys.stderr,
                )
            else:
                warned = True
                print(
                    f"WARNING: {amendment['change_id']}'s changed text is no longer found "
                    f"verbatim in the current full_text — captioned but not highlighted. "
                    f"Something has moved it; worth a look.",
                    file=sys.stderr,
                )

    for spans in diff_blocks.values():
        spans.sort(key=lambda span: span[0])

    if not diff_blocks:
        render_markdown_body(doc, full_text)
        add_amendment_caption(doc, amendments)
        # `warned`, not a hardcoded True: nothing was highlighted, but that is
        # only worth flagging when the changed words have actually gone missing
        # — see the two cases distinguished above.
        return warned

    for start, end, block in blocks:
        spans = diff_blocks.get((start, end))
        if spans:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            render_block_with_diff(p, block, spans)
        else:
            render_markdown_body(doc, block)
    add_amendment_caption(doc, amendments)
    return warned


# --------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------

def fetch_provisions(conn, docx_relpath):
    rows = conn.execute(
        "SELECT provision_id, reference, topic_category, full_text, full_text_anchor, "
        "status, effective_date, notes, latest_change_id "
        "FROM provisions WHERE full_text_path = ? ORDER BY sort_order",
        (docx_relpath,),
    ).fetchall()
    return rows


# One query, used by both exporters (export_excel.py imports it), so the Word
# documents and the Excel tracker can never disagree about what counts as an
# amendment.
QUALIFYING_AMENDMENTS_SQL = """
    SELECT change_id, change_type, old_full_text, new_full_text,
           source_document, detected_timestamp
    FROM change_log
    WHERE provision_id = ?
      AND applied_to_master = 'Y'
      AND change_origin = 'regulatory'
      AND change_type != 'New Provision'
    ORDER BY detected_timestamp DESC, change_id DESC
"""


def fetch_amendments(conn, provision_id):
    """
    Every applied REGULATORY change to this provision, newest first.

    "Regulatory" means the government actually changed the law, as opposed to
    `change_origin='data_correction'`, which is us fixing our own typo or
    paraphrase — those stay in the audit trail and are never highlighted.
    'New Provision' rows are excluded because there is no "before" to show.

    This ASKS FOR the newest qualifying changes. It used to follow
    `provisions.latest_change_id` and then check whether what it found
    qualified — so a data correction applied after a real amendment moved that
    pointer, the check rejected it, and the earlier amendment's highlighting
    disappeared without a word (audit finding H-6). And because only one row
    was ever returned, a provision amended twice only ever showed the second
    amendment (audit finding M-1).
    """
    return conn.execute(QUALIFYING_AMENDMENTS_SQL, (provision_id,)).fetchall()


def fetch_latest_amendment(conn, provision_id):
    """Kept for callers that only want the newest one. Prefer
    fetch_amendments()."""
    rows = fetch_amendments(conn, provision_id)
    return rows[0] if rows else None


def provenance_lines(conn, spec) -> list[str]:
    """
    The "where did this come from and how current is it" lines at the top of
    each document (audit finding L-8).

    "Last regenerated" is deliberately the wording, not "generated on": these
    files are only rebuilt when a change is actually applied, so on a quiet day
    the date on the file is older than today and saying "generated on <today>"
    would be untrue.
    """
    today = date.today().isoformat()
    lines = [
        f"Last regenerated: {today}. This document is generated from the project "
        f"database — do not hand-edit; re-run src/export_word.py after any change "
        f"is applied.",
    ]

    latest = conn.execute(
        "SELECT MAX(last_updated_date) d FROM provisions WHERE full_text_path = ?",
        (spec["path"],),
    ).fetchone()["d"]
    newest_change = conn.execute(
        "SELECT MAX(c.detected_timestamp) t FROM change_log c "
        "JOIN provisions p ON p.provision_id = c.provision_id "
        "WHERE p.full_text_path = ? AND c.applied_to_master = 'Y' "
        "AND c.change_origin = 'regulatory' AND c.change_type != 'New Provision'",
        (spec["path"],),
    ).fetchone()["t"]
    if latest:
        lines.append(f"Text accurate as at: {latest} (the date this database was last updated).")
    if newest_change:
        lines.append(
            f"Most recent government change recorded here: {(newest_change or '')[:10]}."
        )
    lines.extend(spec.get("provenance") or [])
    return lines


def build_document(conn, spec):
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Georgia"
    style.font.size = Pt(10.5)

    title = doc.add_heading(spec["title"], level=0)
    title.runs[0].font.color.rgb = HEADING_COLOR

    sub = doc.add_paragraph(spec["subtitle"])
    sub.runs[0].font.size = Pt(9)
    sub.runs[0].font.color.rgb = GREY
    sub.runs[0].italic = True

    for line in provenance_lines(conn, spec):
        note = doc.add_paragraph(line)
        note.runs[0].font.size = Pt(9)
        note.runs[0].font.color.rgb = GREY

    disclaimer = doc.add_paragraph(DISCLAIMER)
    disclaimer.runs[0].font.size = Pt(9)
    disclaimer.runs[0].font.color.rgb = GREY
    disclaimer.runs[0].bold = True

    doc.add_page_break()

    toc_heading = doc.add_heading("Table of Contents", level=1)
    toc_heading.runs[0].font.color.rgb = HEADING_COLOR

    provisions = fetch_provisions(conn, spec["path"])
    warnings = []

    bookmark_id = 1
    for row in provisions:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        add_internal_hyperlink(p, f"{row['reference']} — {row['topic_category']}", row["full_text_anchor"])

    doc.add_page_break()

    for row in provisions:
        heading = doc.add_heading(row["reference"], level=2)
        heading.runs[0].font.color.rgb = HEADING_COLOR
        add_bookmark(heading, row["full_text_anchor"], bookmark_id)
        bookmark_id += 1

        meta = doc.add_paragraph()
        meta_run = meta.add_run(
            f"{row['topic_category']}  |  Status: {row['status']}  |  Effective: {row['effective_date']}"
        )
        meta_run.font.size = Pt(8.5)
        meta_run.font.color.rgb = GREY
        meta_run.italic = True
        meta.paragraph_format.space_after = Pt(10)

        amendments = fetch_amendments(conn, row["provision_id"])
        warned = render_provision_body(doc, row["full_text"], amendments)
        if warned:
            warnings.append(row["provision_id"])

        if row["notes"]:
            note_p = doc.add_paragraph()
            note_run = note_p.add_run(f"Note: {row['notes']}")
            note_run.italic = True
            note_run.font.size = Pt(8.5)
            note_run.font.color.rgb = GREY

        doc.add_paragraph()  # spacing between provisions

    return doc, len(provisions), warnings


def main():
    conn = get_connection()
    for spec in DOCX_SPECS:
        doc, count, warnings = build_document(conn, spec)
        out_path = PROJECT_ROOT / spec["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path)
        print(f"Wrote {count} provisions -> {out_path}")
        if warnings:
            print(f"  {len(warnings)} warning(s), see stderr: {', '.join(warnings)}")
    conn.close()


if __name__ == "__main__":
    main()
