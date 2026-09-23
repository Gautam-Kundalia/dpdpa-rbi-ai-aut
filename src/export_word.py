"""
Generate DPDP_Rules_2025.docx and DPDP_Act_2023.docx from db/dpdpa.db.

Layout mirrors the actual Gazette structure: each provision is a heading
(bookmarked, for linking from Excel) followed by its verbatim clause text.
A manual, clickable table of contents sits at the top of each document.

Amendment convention (once the pipeline starts detecting real changes):
new text is highlighted yellow; the superseded text is shown directly
below it, struck through, under a "Previous text (superseded)" label.
This only activates for provisions whose latest applied change has
change_type != 'New Provision' and has old_full_text populated — right
now, on the initial baseline load, nothing triggers it.

Usage:
    python src/export_word.py
"""
from __future__ import annotations

import re

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from db import PROJECT_ROOT, get_connection

DOCX_SPECS = [
    {
        "path": "docs/DPDP_Rules_2025.docx",
        "title": "The Digital Personal Data Protection Rules, 2025",
        "subtitle": "Consolidated text, generated from db/dpdpa.db — Source: Gazette Notification "
                     "G.S.R. 846(E), dated 13 November 2025",
    },
    {
        "path": "docs/DPDP_Act_2023.docx",
        "title": "The Digital Personal Data Protection Act, 2023",
        "subtitle": "Consolidated text, generated from db/dpdpa.db — Source: Act No. 22 of 2023, "
                     "as notified in phases per G.S.R. 843(E), dated 13 November 2025",
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


def fetch_latest_amendment(conn, provision_id):
    """
    Returns the change that provisions.latest_change_id points at IF it
    represents an actual regulatory amendment (not the initial 'New Provision'
    load). Keying on latest_change_id — rather than "the newest change_log row
    of any non-'New Provision' type" — is what lets one-time internal data
    corrections (change_log rows that deliberately do NOT repoint
    latest_change_id, e.g. CHG-0033..CHG-0039) stay in the audit trail without
    being rendered as if the government had amended the law.
    """
    row = conn.execute(
        "SELECT c.change_type, c.old_full_text, c.new_full_text "
        "FROM provisions p JOIN change_log c ON c.change_id = p.latest_change_id "
        "WHERE p.provision_id = ? AND c.applied_to_master = 'Y' "
        "AND c.change_type != 'New Provision'",
        (provision_id,),
    ).fetchone()
    return row


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

    note = doc.add_paragraph(
        "This document is generated from the project database — do not hand-edit; "
        "re-run src/export_word.py after any change is approved."
    )
    note.runs[0].font.size = Pt(9)
    note.runs[0].font.color.rgb = GREY

    doc.add_page_break()

    toc_heading = doc.add_heading("Table of Contents", level=1)
    toc_heading.runs[0].font.color.rgb = HEADING_COLOR

    provisions = fetch_provisions(conn, spec["path"])

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

        amendment = fetch_latest_amendment(conn, row["provision_id"])
        if amendment and amendment["new_full_text"]:
            render_markdown_body(doc, amendment["new_full_text"], highlight=True)
            if amendment["old_full_text"]:
                prev_label = doc.add_paragraph()
                prev_run = prev_label.add_run("Previous text (superseded):")
                prev_run.bold = True
                prev_run.font.size = Pt(9)
                prev_run.font.color.rgb = GREY
                render_markdown_body(doc, amendment["old_full_text"], strike=True)
        else:
            render_markdown_body(doc, row["full_text"])

        if row["notes"]:
            note_p = doc.add_paragraph()
            note_run = note_p.add_run(f"Note: {row['notes']}")
            note_run.italic = True
            note_run.font.size = Pt(8.5)
            note_run.font.color.rgb = GREY

        doc.add_paragraph()  # spacing between provisions

    return doc, len(provisions)


def main():
    conn = get_connection()
    for spec in DOCX_SPECS:
        doc, count = build_document(conn, spec)
        out_path = PROJECT_ROOT / spec["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path)
        print(f"Wrote {count} provisions -> {out_path}")
    conn.close()


if __name__ == "__main__":
    main()
