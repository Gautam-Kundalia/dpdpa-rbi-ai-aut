"""
Generate the human-facing Excel tracker from db/dpdpa.db.

SQLite is the source of truth; this script is meant to be re-run any time
the DB changes (manually for now, later on a schedule after each pipeline
run) to refresh data/DPDP_Rules_Tracker.xlsx.

Usage:
    python src/export_excel.py
"""
from __future__ import annotations

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from db import PROJECT_ROOT, get_connection

FONT_NAME = "Arial"
HEADER_FILL = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
HEADER_FONT = Font(name=FONT_NAME, size=10, bold=True, color="FFFFFF")
INPUT_HEADER_FILL = PatternFill(start_color="BF9000", end_color="BF9000", fill_type="solid")
COMPUTED_HEADER_FILL = PatternFill(start_color="548235", end_color="548235", fill_type="solid")  # green = computed
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

OUT_PATH = PROJECT_ROOT / "data" / "DPDP_Rules_Tracker.xlsx"

MP_COLS = [
    "provision_id", "instrument_type", "reference", "topic_category",
    "current_summary", "full_text_path", "full_text_anchor", "status", "effective_date",
    "last_updated_date", "source_document", "source_url",
    "confidence_score", "review_status", "reviewed_by", "review_date",
    "latest_change_id", "notes",
]
MP_INPUT_COLS = {"review_status", "reviewed_by", "review_date"}
MP_COL_IDX = {c: i for i, c in enumerate(MP_COLS, start=1)}
EFFECTIVE_DATE_COL_LETTER = get_column_letter(MP_COL_IDX["effective_date"])
IN_FORCE_COL_IDX = len(MP_COLS) + 1  # appended as the last column

CL_COLS = [
    "change_id", "detected_timestamp", "provision_id", "change_type",
    "old_value_summary", "new_value_summary", "source_document", "source_url",
    "detected_by", "confidence_score", "review_status", "reviewed_by",
    "review_date", "applied_to_master", "notes",
]
CL_INPUT_COLS = {"review_status", "reviewed_by", "review_date", "applied_to_master"}
CL_COL_IDX = {c: i for i, c in enumerate(CL_COLS, start=1)}

SL_COLS = [
    "document_id", "source", "title", "url", "published_date",
    "fetched_date", "content_hash", "processing_status", "linked_change_ids",
]
SL_COL_IDX = {c: i for i, c in enumerate(SL_COLS, start=1)}

MAX_DATA_ROW = 2000  # validations apply down to this row so future rows keep dropdowns


def style_header_cell(ws, row, col, fill):
    cell = ws.cell(row=row, column=col)
    cell.fill = fill
    cell.font = HEADER_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = BORDER


def style_header(ws, ncols, input_cols_idx, row=1, computed_cols_idx=frozenset()):
    for c in range(1, ncols + 1):
        if c in computed_cols_idx:
            fill = COMPUTED_HEADER_FILL
        elif c in input_cols_idx:
            fill = INPUT_HEADER_FILL
        else:
            fill = HEADER_FILL
        style_header_cell(ws, row, c, fill)
    ws.freeze_panes = ws.cell(row=row + 1, column=1)
    ws.row_dimensions[row].height = 32


def set_widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def write_rows(ws, cols, rows, start_row=2, full_text_col=None, anchor_col=None):
    r = start_row - 1
    for r, row in enumerate(rows, start=start_row):
        for c, col in enumerate(cols, start=1):
            val = row[col] if col in row.keys() else None
            cell = ws.cell(row=r, column=c, value=val)
            cell.border = BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if full_text_col and col == full_text_col and val:
                anchor = row[anchor_col] if anchor_col and anchor_col in row.keys() else None
                target = str(PROJECT_ROOT / val)
                if anchor:
                    target = f"{target}#{anchor}"
                cell.hyperlink = target
                cell.value = "Open full text"
                cell.font = Font(name=FONT_NAME, size=10, color="0563C1", underline="single")
    return r


def add_list_validation(ws, col_idx, options, first_row=2, last_row=MAX_DATA_ROW):
    col_letter = get_column_letter(col_idx)
    dv = DataValidation(
        type="list",
        formula1='"{}"'.format(",".join(options)),
        allow_blank=True,
        showDropDown=False,  # openpyxl quirk: False = show the dropdown arrow
    )
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}{first_row}:{col_letter}{last_row}")


def add_in_force_column(ws, last_data_row):
    """
    Computed column: Yes/No based on comparing today's date to Effective_Date.
    Never manually edited, never goes stale, and can't contradict Notes/Status
    the way a hand-maintained flag could.
    """
    style_header_cell(ws, 1, IN_FORCE_COL_IDX, COMPUTED_HEADER_FILL)
    ws.cell(row=1, column=IN_FORCE_COL_IDX, value="In_Force")
    ws.column_dimensions[get_column_letter(IN_FORCE_COL_IDX)].width = 11

    for r in range(2, last_data_row + 1):
        eff_cell = f"{EFFECTIVE_DATE_COL_LETTER}{r}"
        formula = f'=IF({eff_cell}="","",IF(TODAY()>=DATEVALUE({eff_cell}),"Yes","No"))'
        cell = ws.cell(row=r, column=IN_FORCE_COL_IDX, value=formula)
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")


def main():
    conn = get_connection()

    provisions = conn.execute(f"SELECT {','.join(MP_COLS)} FROM provisions ORDER BY sort_order").fetchall()
    changes = conn.execute(f"SELECT {','.join(CL_COLS)} FROM change_log ORDER BY detected_timestamp").fetchall()
    sources = conn.execute(f"SELECT {','.join(SL_COLS)} FROM source_log ORDER BY fetched_date").fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    build_readme(wb)

    # --- Master_Provisions ---
    mp = wb.create_sheet("Master_Provisions")
    for i, h in enumerate(MP_COLS, start=1):
        mp.cell(row=1, column=i, value=h.replace("_", " ").title().replace(" ", "_"))
    input_idx = {i for i, c in enumerate(MP_COLS, start=1) if c in MP_INPUT_COLS}
    style_header(mp, len(MP_COLS), input_idx)
    set_widths(mp, [14, 14, 22, 20, 42, 24, 16, 12, 14, 16, 26, 30, 12, 16, 14, 14, 14, 30])
    last_row = write_rows(mp, MP_COLS, provisions, full_text_col="full_text_path", anchor_col="full_text_anchor")
    add_in_force_column(mp, max(last_row, 2))

    add_list_validation(mp, MP_COL_IDX["instrument_type"],
                         ["Act Section", "Rule", "Sub-Rule", "Schedule", "Notification", "Board Order"])
    add_list_validation(mp, MP_COL_IDX["topic_category"],
                         ["Consent & Notice", "Data Principal Rights", "Retention & Erasure",
                          "Breach Notification", "Children & Persons with Disabilities",
                          "Cross-Border Transfer", "Consent Manager", "Significant Data Fiduciary",
                          "Data Protection Board", "Penalties", "Exemptions", "Definitions", "Other"])
    add_list_validation(mp, MP_COL_IDX["status"], ["Active", "Draft", "Superseded", "Repealed"])
    add_list_validation(mp, MP_COL_IDX["review_status"], ["Confirmed", "Pending Review", "Rejected"])

    # --- Change_Log ---
    cl = wb.create_sheet("Change_Log")
    for i, h in enumerate(CL_COLS, start=1):
        cl.cell(row=1, column=i, value=h.replace("_", " ").title().replace(" ", "_"))
    input_idx = {i for i, c in enumerate(CL_COLS, start=1) if c in CL_INPUT_COLS}
    style_header(cl, len(CL_COLS), input_idx)
    set_widths(cl, [12, 18, 14, 16, 36, 36, 26, 30, 20, 12, 16, 14, 14, 14, 28])
    write_rows(cl, CL_COLS, changes)

    add_list_validation(cl, CL_COL_IDX["change_type"],
                         ["New Provision", "Amendment", "Repeal", "Clarification", "Correction"])
    add_list_validation(cl, CL_COL_IDX["review_status"],
                         ["Pending Review", "Approved", "Rejected", "Modified"])
    add_list_validation(cl, CL_COL_IDX["applied_to_master"], ["Y", "N"])

    # --- Source_Log ---
    sl = wb.create_sheet("Source_Log")
    for i, h in enumerate(SL_COLS, start=1):
        sl.cell(row=1, column=i, value=h.replace("_", " ").title().replace(" ", "_"))
    style_header(sl, len(SL_COLS), set())
    set_widths(sl, [14, 12, 40, 34, 16, 16, 22, 18, 20])
    write_rows(sl, SL_COLS, sources)

    add_list_validation(sl, SL_COL_IDX["source"],
                         ["MeitY", "eGazette", "PIB", "Data Protection Board", "Other"])
    add_list_validation(sl, SL_COL_IDX["processing_status"],
                         ["New", "Processed", "No Change Detected", "Error"])

    wb.active = 0
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_PATH)
    print(f"Exported {len(provisions)} provisions, {len(changes)} changes, "
          f"{len(sources)} sources -> {OUT_PATH}")


def build_readme(wb):
    readme = wb.create_sheet("README")
    readme.sheet_view.showGridLines = False
    set_widths(readme, [32, 100])

    title = readme.cell(row=1, column=1, value="DPDP Regulatory Change Tracker")
    title.font = Font(name=FONT_NAME, size=14, bold=True, color="1F3864")
    readme.merge_cells("A1:B1")

    sub = readme.cell(row=2, column=1,
                       value="Generated from db/dpdpa.db — SQLite is the source of truth, "
                             "this file is the human-facing view. Re-run src/export_excel.py "
                             "any time the database changes; hand-edits here won't persist.")
    sub.font = Font(name=FONT_NAME, size=10, italic=True, color="595959")
    readme.merge_cells("A2:B2")

    def section(row, heading):
        c = readme.cell(row=row, column=1, value=heading)
        c.font = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
        readme.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        return row + 1

    def para(row, label, text):
        l = readme.cell(row=row, column=1, value=label)
        l.font = Font(name=FONT_NAME, size=10, bold=True)
        l.alignment = Alignment(vertical="top", wrap_text=True)
        t = readme.cell(row=row, column=2, value=text)
        t.font = Font(name=FONT_NAME, size=10)
        t.alignment = Alignment(vertical="top", wrap_text=True)
        return row + 1

    r = 4
    r = section(r, "What this workbook is for")
    r = para(r, "Purpose",
             "Tracks every provision of the DPDP Act, 2023 and DPDP Rules, 2025 in its "
             "current, correct form (Master_Provisions), keeps a permanent append-only "
             "record of every detected change (Change_Log), and logs every source document "
             "the agent has checked (Source_Log).")
    r += 1

    r = section(r, "Sheet guide")
    r = para(r, "Master_Provisions",
             "One row per provision (an Act section, Rule, or Schedule clause). This is the "
             "'current state' view a consultant reads. Full_Text_Path is a clickable link "
             "that opens the full clause text in the consolidated Word document "
             "(DPDP_Rules_2025.docx or DPDP_Act_2023.docx), jumping straight to that "
             "provision's bookmark.")
    r = para(r, "Change_Log",
             "Append-only. One row per detected change, whether or not it has been approved. "
             "Never edit or delete past rows — that history is the audit trail. Provision_ID "
             "links a change back to its row in Master_Provisions.")
    r = para(r, "Source_Log",
             "One row per source document the agent has fetched (MeitY page, Gazette "
             "notification, PIB release). Prevents reprocessing the same document twice and "
             "gives you a paper trail of what was checked and when.")
    r += 1

    r = section(r, "Status vs. In_Force — these answer different questions")
    r = para(r, "Status",
             "Is this validly enacted law at all? Active = currently valid law (even if not "
             "yet commenced — see In_Force). Draft = proposed but not yet notified. "
             "Superseded = replaced by a later amendment. Repealed = withdrawn.")
    r = para(r, "In_Force",
             "Computed automatically (green header) by comparing today's date to "
             "Effective_Date — Yes if commenced, No if not yet. This updates itself every "
             "time the file is opened; never edit it by hand. A provision can be Status=Active "
             "but In_Force=No if it's validly notified but its commencement date hasn't "
             "arrived yet (both the Act and the Rules stagger commencement across several "
             "dates — see Notes on each row).")
    r += 1

    r = section(r, "Full text & amendment highlighting")
    r = para(r, "Where full text lives",
             "Verbatim clause text is stored in the database and rendered into the two "
             "consolidated Word documents by src/export_word.py — never duplicated or "
             "paraphrased here.")
    r = para(r, "Amendment convention",
             "When a future change updates a clause, the Word document highlights the new "
             "text in yellow and shows the superseded text struck through directly below it, "
             "under a 'Previous text (superseded)' label — so nothing is silently lost, and "
             "what changed is visible at a glance in context.")
    r += 1

    r = section(r, "Color legend")
    c1 = readme.cell(row=r, column=1, value="")
    c1.fill = INPUT_HEADER_FILL
    readme.cell(row=r, column=2,
                value="Gold column headers are for human review input — Review_Status, "
                      "Reviewed_By, Review_Date, etc.")
    readme.cell(row=r, column=2).font = Font(name=FONT_NAME, size=10)
    readme.cell(row=r, column=2).alignment = Alignment(wrap_text=True)
    r += 1
    c2 = readme.cell(row=r, column=1, value="")
    c2.fill = COMPUTED_HEADER_FILL
    readme.cell(row=r, column=2,
                value="Green column headers are computed by formula — never edit these by "
                      "hand, they'll be overwritten and are self-updating anyway.")
    readme.cell(row=r, column=2).font = Font(name=FONT_NAME, size=10)
    readme.cell(row=r, column=2).alignment = Alignment(wrap_text=True)
    r += 1
    readme.cell(row=r, column=2,
                value="Everything else (dark blue headers) is populated by the agent from source documents.")
    readme.cell(row=r, column=2).font = Font(name=FONT_NAME, size=10)
    readme.cell(row=r, column=2).alignment = Alignment(wrap_text=True)
    r += 2

    r = section(r, "Recommended workflow")
    r = para(r, "1. Detect", "Agent checks Source_Log-tracked sources on schedule; new/changed documents get a new Source_Log row.")
    r = para(r, "2. Extract & classify", "Agent extracts provisions and proposes a Change_Log row (Change_Type, Old/New value, Confidence).")
    r = para(r, "3. Review", "Anything below the confidence threshold (or any change to a number, deadline, or obligation) sits with Review_Status = Pending Review until a consultant checks it.")
    r = para(r, "4. Apply", "Once approved, Master_Provisions is updated, Change_Log's Applied_To_Master is marked Y, and re-running export_word.py renders the amendment highlight into the consolidated document. Rejected changes stay in Change_Log for the record but never touch Master_Provisions or the docx.")

    for row in readme.iter_rows(min_row=1, max_row=r, min_col=1, max_col=2):
        for cell in row:
            if cell.value:
                cell.alignment = Alignment(wrap_text=True, vertical="top")


if __name__ == "__main__":
    main()
