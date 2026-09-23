"""
Phase 4c (23 Sep 2026 audit fixes): apply the 5 pre-approved summary
(current_summary) fixes from the audit's draft script
(docs/audit_2026-09-23/DRAFT_apply_audit_fixes_2026-09-23.py), and no others
— these are data corrections (the government didn't change anything;
we're fixing our own plain-language summaries), so change_origin=
'data_correction' and never highlighted.

Ground rule: don't rewrite summaries freely. Each fix here checks the
CURRENT summary against the exact "before" text the audit session found —
if a row has since diverged (its summary was changed again by something
else since the audit), that row is SKIPPED and reported, not forced. This
is not hypothetical: as of this run, 2 of the 5 (DPDPA-S44.2 and
DPDPA-S44.1_3) no longer match the audit's expected "before" text — see
main()'s output.

Usage:
    python scripts/apply_summary_fixes_2026-09-23.py --dry-run   (default)
    python scripts/apply_summary_fixes_2026-09-23.py --apply
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from db import get_connection, init_schema, next_id  # noqa: E402

# (provision_id, expected current summary, new summary, basis) — copied
# verbatim from docs/audit_2026-09-23/DRAFT_apply_audit_fixes_2026-09-23.py's
# SUMMARIES list (the audit's own text, not retyped/reworded here).
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default=None, help="Override db/dpdpa.db path (testing only)")
    args = ap.parse_args()

    conn = get_connection(Path(args.db)) if args.db else get_connection()
    init_schema(conn)

    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    to_apply, skipped = [], []
    for pid, expected_old, new, basis in SUMMARIES:
        row = conn.execute("SELECT current_summary FROM provisions WHERE provision_id = ?", (pid,)).fetchone()
        if row is None:
            skipped.append((pid, "provision not found"))
            continue
        current = row["current_summary"]
        if current == expected_old:
            to_apply.append((pid, expected_old, new, basis))
            print(f"  {pid}: matches expected — will apply")
        elif current == new:
            skipped.append((pid, "already applied (current summary matches the new text)"))
            print(f"  {pid}: already reads as the corrected text — nothing to do")
        else:
            skipped.append((pid, "current summary has diverged from what the audit expected — needs Gautam's review, not auto-applied"))
            print(f"  {pid}: SKIPPED — current summary doesn't match the audit's expected 'before' text")
            print(f"    expected: {expected_old!r}")
            print(f"    actual:   {current!r}")

    print(f"\n{'APPLYING' if args.apply else 'DRY RUN — would apply'} {len(to_apply)} summary fix(es): "
          f"{[p for p, *_ in to_apply]}")
    if skipped:
        print(f"Skipped {len(skipped)}: " + "; ".join(f"{p} ({why})" for p, why in skipped))

    if not args.apply:
        print("\nDry run complete. Re-run with --apply to write changes.")
        conn.close()
        return 0

    change_ids = []
    for pid, old, new, basis in to_apply:
        cid = next_id(conn, "change_log", "change_id", "CHG")
        conn.execute(
            """INSERT INTO change_log
               (change_id, detected_timestamp, provision_id, change_type, change_origin,
                old_value_summary, new_value_summary, source_document, detected_by,
                confidence_score, review_status, reviewed_by, review_date, applied_to_master, notes)
               VALUES (?, ?, ?, 'Correction', 'data_correction', ?, ?, 'Audit 2026-09-23',
                       'manual:audit-2026-09-23-summary-fix', 1.0, 'Pending Review', NULL, NULL, 'Y', ?)""",
            (cid, now, pid, old, new,
             f"Summary-only data-quality fix (not a regulatory change; never highlighted). Basis: {basis}"),
        )
        conn.execute(
            "UPDATE provisions SET current_summary = ?, last_updated_date = ? WHERE provision_id = ?",
            (new, today, pid),
        )
        change_ids.append(cid)
        print(f"  {pid}: applied as {cid}")

    conn.commit()
    conn.close()
    print(f"\nDone. change_ids: {change_ids}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
