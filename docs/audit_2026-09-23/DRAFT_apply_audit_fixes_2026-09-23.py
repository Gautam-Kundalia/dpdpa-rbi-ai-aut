"""
DRAFT — prepared during the 2026-09-23 audit. NOT RUN. Review every
before/after below against the quoted sources before running.

Two groups of changes:

  A. G.S.R. 892(E) corrigendum to the DPDP Rules (a real government act,
     dated 10 Dec 2025, Gazette Extraordinary No. 806 of 11 Dec 2025,
     e-Gazette ID CG-DL-E-12122025-268455). Source PDF (MeitY-hosted):
     https://www.meity.gov.in/static/uploads/2025/12/3c7ebbae0e5456f493f486e6845df86b.pdf
     SHA-256 8f8d9526b511801889f8ae022b6d7c5db449283e90fe32792e5896314b32f994
     Only the corrigendum items that touch text the DB actually holds are
     applied. First Schedule "every body" is already correct in the DB;
     the First/Fourth Schedule Notes it corrects are not in the DB at all
     (omitted at seeding: a separate decision).

  B. Summary-only fixes (current_summary), no full_text change.

DECISION NEEDED BEFORE RUNNING (the script refuses to run until set):
  HIGHLIGHT_CORRIGENDUM = True  -> treat G.S.R. 892(E) as a real regulatory
      change: point provisions.latest_change_id at the new rows, so the
      Rules Word doc shows it with the yellow/strikethrough convention.
  HIGHLIGHT_CORRIGENDUM = False -> record it the same way as tonight's
      Act data corrections (audit trail only, no highlight).
  Note: export_word.py only honours this choice once the drafted
  export_word.py fix (key highlighting on latest_change_id) is in place.
"""
import sqlite3
import sys
from datetime import datetime, timezone

HIGHLIGHT_CORRIGENDUM = None  # <- Gautam: set True or False

DB_PATH = "db/dpdpa.db"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
TODAY = NOW[:10]
GSR892_URL = "https://www.meity.gov.in/static/uploads/2025/12/3c7ebbae0e5456f493f486e6845df86b.pdf"
GSR892_DOC = "Corrigenda G.S.R. 892(E), 10 Dec 2025 (Gazette Extraordinary No. 806, 11 Dec 2025)"

# (provision_id, exact old substring, new substring, corrigendum item)
CORRIGENDUM = [
    ("DPDPR-R1",
     "(3) Rule 4 shall come into force one year after the date of publication of this Gazette.",
     "(3) Rule 4 shall come into force one year after the date of publication in the Official Gazette.",
     "item (i)(a): page 24, line 22, for “of this Gazette”, read “in the Official Gazette”"),
    ("DPDPR-R1",
     "eighteen months after the date of publication of this Gazette.",
     "eighteen months after the date of publication in the Official Gazette.",
     "item (i)(b): page 24, line 24, for “of this Gazette”, read “in the Official Gazette”"),
    ("DPDPR-SDF-R13",
     "other Ministries or Department of the Central Government.",
     "other Ministries or Departments of the Central Government.",
     "item (ii): page 29, line 44, for “Department”, read “Departments”"),
    ("DPDPR-R23",
     "within the specified period as may be given in such.",
     "within the specified period as may be given in such order.",
     "item (iii): page 32, line 4, for “given in such”, read “given in such order”"),
]

# (provision_id, exact current summary, new summary, source/basis)
SUMMARIES = [
    ("DPDPA-S6.9",
     "Every Consent Manager must be registered with the Board, subject to prescribed technical, operational, and financial conditions. (This sub-clause commences a year after the rest of Section 6, alongside Rule 4's registration process.)",
     "Every Consent Manager must be registered with the Board, subject to prescribed technical, operational, financial and other conditions. (This sub-section commences one year after publication of G.S.R. 843(E) — six months BEFORE the rest of Section 6 — alongside Rule 4's registration process.)",
     "G.S.R. 843(E) clause (b) (one year) vs clause (c) (eighteen months: 'sub-sections (1) to (8) and (10) of section 6')"),
    ("DPDPA-S27.1d",
     "Gives the Board the power to inquire into, and penalise, a breach of Consent Manager registration conditions. (Commences a year after the rest of Section 27, alongside Section 6(9)'s Consent Manager registration requirement.)",
     "Gives the Board the power to inquire into, and penalise, a breach of Consent Manager registration conditions. (Commences one year after publication of G.S.R. 843(E) — six months BEFORE the rest of Section 27 — alongside Section 6(9)'s Consent Manager registration requirement.)",
     "G.S.R. 843(E) clause (b) vs clause (c) ('section 27 except clause (d) of sub-section (1)')"),
    ("DPDPA-S44.2",
     "Amends the Information Technology Act, 2000 — removes the old compensation-for-data-breach provision (Section 43A, since this Act now governs that), inserts a cross-reference to this Act into Section 81's proviso, and omits a now-redundant RTI-exemption clause (Section 87(2)(ob)).",
     "Amends the Information Technology Act, 2000 — omits Section 43A (the old compensation-for-data-breach provision), inserts a reference to this Act into Section 81's proviso, and omits Section 87(2)(ob) (the rule-making power for Section 43A's reasonable security practices and sensitive personal data).",
     "IT Act s.87(2)(ob): 'the reasonable security practices and procedures and sensitive personal data or information under section 43A' — not an RTI clause"),
    ("DPDPA-S44.1_3",
     "Amends the TRAI Act, 1997 to replace its Appellate Tribunal list with the IT Act, Airports Economic Regulatory Authority Act, and DPDP Act Appellate Tribunals, and amends the RTI Act, 2005 to add a standalone exemption for 'information which relates to personal information'.",
     "Amends the TRAI Act, 1997 by substituting sub-clauses (i) and (ii) of section 14(c) with a list covering the IT Act, Airports Economic Regulatory Authority Act and DPDP Act Appellate Tribunals, and amends the RTI Act, 2005 by substituting clause (j) of section 8(1) with 'information which relates to personal information'.",
     "Act s.44(1) and (3): both are substitutions ('the following ... shall be substituted'), not additions"),
    ("DPDPR-R12",
     "Exempts specified classes of Data Fiduciary (healthcare providers, educational institutions, crèches, child transport providers — Fourth Schedule Part A) and specified purposes (Part B, e.g. safety tracking, email accounts) from the Act's general prohibition on tracking/behavioural monitoring/targeted ads directed at children.",
     "Exempts specified classes of Data Fiduciary (healthcare providers, educational institutions, crèches, child transport providers — Fourth Schedule Part A) and specified purposes (Part B, e.g. safety tracking, email accounts) from BOTH the verifiable parental consent requirement (s.9(1)) and the bar on tracking/behavioural monitoring/targeted ads directed at children (s.9(3)), subject to the Schedule's conditions.",
     "Rule 12(1),(2): 'The provisions of sub-sections (1) and (3) of section 9 of the Act shall not be applicable'"),
]


def next_chg(conn):
    n = 0
    for (cid,) in conn.execute("SELECT change_id FROM change_log WHERE change_id LIKE 'CHG-%'"):
        try:
            n = max(n, int(cid.split("-")[-1]))
        except ValueError:
            pass
    return f"CHG-{n + 1:04d}"


def main():
    if HIGHLIGHT_CORRIGENDUM is None:
        sys.exit("Set HIGHLIGHT_CORRIGENDUM to True or False first (see docstring).")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        # A. corrigendum, grouped per provision
        by_pid = {}
        for pid, old, new, item in CORRIGENDUM:
            by_pid.setdefault(pid, []).append((old, new, item))
        for pid, edits in by_pid.items():
            (before,) = conn.execute("SELECT full_text FROM provisions WHERE provision_id=?", (pid,)).fetchone()
            after = before
            for old, new, _ in edits:
                if after.count(old) != 1:
                    raise SystemExit(f"{pid}: expected exactly one match for {old!r}; aborting, nothing written")
                after = after.replace(old, new)
            cid = next_chg(conn)
            conn.execute(
                """INSERT INTO change_log (change_id, detected_timestamp, provision_id, change_type,
                   old_value_summary, new_value_summary, old_full_text, new_full_text, source_document,
                   source_url, detected_by, confidence_score, review_status, applied_to_master, notes)
                   VALUES (?,?,?,'Correction',?,?,?,?,?,?,?,1.0,'Pending Review','Y',?)""",
                (cid, NOW, pid, "Text as originally gazetted in G.S.R. 846(E)",
                 "Text as corrected by G.S.R. 892(E)", before, after, GSR892_DOC, GSR892_URL,
                 "manual:audit-2026-09-23 (text taken from the official corrigendum PDF)",
                 "Government corrigendum (regulatory change, missed at seeding): " + "; ".join(i for _, _, i in edits)),
            )
            sets = "full_text=?, last_updated_date=?, notes=COALESCE(notes,'') || ?"
            args = [after, TODAY, f" Text updated {TODAY} per corrigendum G.S.R. 892(E) ({cid})."]
            if HIGHLIGHT_CORRIGENDUM:
                sets += ", latest_change_id=?"
                args.append(cid)
            conn.execute(f"UPDATE provisions SET {sets} WHERE provision_id=?", (*args, pid))
            print(f"{pid}: corrigendum applied as {cid}")

        # B. summaries
        for pid, old, new, basis in SUMMARIES:
            (cur,) = conn.execute("SELECT current_summary FROM provisions WHERE provision_id=?", (pid,)).fetchone()
            if cur != old:
                raise SystemExit(f"{pid}: current_summary is not what the draft expected; aborting, nothing written")
            cid = next_chg(conn)
            conn.execute(
                """INSERT INTO change_log (change_id, detected_timestamp, provision_id, change_type,
                   old_value_summary, new_value_summary, source_document, detected_by, confidence_score,
                   review_status, applied_to_master, notes)
                   VALUES (?,?,?,'Correction',?,?,?,?,1.0,'Pending Review','Y',?)""",
                (cid, NOW, pid, old, new, "Audit 2026-09-23", "manual:audit-2026-09-23",
                 "Summary-only data-quality fix (not a regulatory change). Basis: " + basis),
            )
            conn.execute("UPDATE provisions SET current_summary=?, last_updated_date=? WHERE provision_id=?",
                         (new, TODAY, pid))
            print(f"{pid}: summary corrected as {cid}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
