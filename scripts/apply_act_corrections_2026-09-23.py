import sqlite3
from datetime import date

DB_PATH = "db/dpdpa.db"
TODAY = date.today().isoformat()
PDF_HASH = "4deb23981d3010c8225a2ff6149e7243dc2268455b299e283afebdd7b72a7d15"
CORRECTION_NOTE = (
    f" Text corrected {TODAY} against the official Act PDF "
    f"(SHA-256 {PDF_HASH[:8]}...{PDF_HASH[-4:]}), re-verified against a "
    f"hash-confirmed copy of the source PDF (second extraction pass; "
    f"Sonnet+Opus review) — see docs/act_table_audit_2026-09-23.md."
)

CORRECTIONS = {}

CORRECTIONS["DPDPA-S7"] = (
"""**Section 7 — Certain legitimate uses**

A Data Fiduciary may process personal data of a Data Principal for any of the following legitimate uses, namely —

(a) for the specified purpose for which the Data Principal has voluntarily provided her personal data to the Data Fiduciary, and in respect of which she has not indicated to the Data Fiduciary that she does not consent to the use of her personal data;

(b) for the State and any of its instrumentalities to provide or issue to the Data Principal such subsidy, benefit, service, certificate, licence or permit as may be prescribed, where —
(i) she has previously consented to the processing of her personal data by the State or any of its instrumentalities for any subsidy, benefit, service, certificate, licence or permit; or
(ii) such personal data is available in digital form in, or in non-digital form and digitised subsequently from, any database, register, book or other document which is maintained by the State or any of its instrumentalities and is notified by the Central Government,
subject to standards followed for processing being in accordance with the policy issued by the Central Government or any law for the time being in force for governance of personal data;

(c) for the performance by the State or any of its instrumentalities of any function under any law for the time being in force in India, or in the interest of sovereignty and integrity of India or security of the State;

(d) for fulfilling any obligation under any law for the time being in force in India on any person to disclose any information to the State or any of its instrumentalities, subject to such processing being in accordance with the provisions regarding disclosure of such information in any other law for the time being in force;

(e) for compliance with any judgment or decree or order issued under any law for the time being in force in India, or any judgment or order relating to claims of a contractual or civil nature under any law in force outside India;

(f) for responding to a medical emergency involving a threat to the life or immediate threat to the health of the Data Principal or any other individual;

(g) for taking measures to provide medical treatment or health services to any individual during an epidemic, outbreak of disease, or any other threat to public health;

(h) for taking measures to ensure safety of, or provide assistance or services to, any individual during any disaster, or any breakdown of public order; or

(i) for the purposes of employment or those related to safeguarding the employer from loss or liability, such as prevention of corporate espionage, maintenance of confidentiality of trade secrets, intellectual property, classified information or provision of any service or benefit sought by a Data Principal who is an employee.""",
    None,
)

CORRECTIONS["DPDPA-S26"] = (
"""**Section 26 — Powers of Chairperson**

The Chairperson shall exercise the following powers, namely —

(a) general superintendence and giving direction in respect of all administrative matters of the Board;

(b) authorise any officer of the Board to scrutinise any intimation, complaint, reference or correspondence addressed to the Board; and

(c) authorise performance of any of the functions of the Board and conduct any of its proceedings, by an individual Member or groups of Members and to allocate proceedings among them.""",
    "Gives the Chairperson general superintendence over Board administrative matters, the power to authorise any officer to scrutinise matters addressed to the Board, and the power to delegate specific functions and proceedings to an individual Member or groups of Members.",
)

CORRECTIONS["DPDPA-S17"] = (
"""**Section 17 — Exemptions**

(1) The provisions of Chapter II, except sub-sections (1) and (5) of section 8, and those of Chapter III and section 16 shall not apply where — (a) the processing of personal data is necessary for enforcing any legal right or claim; (b) the processing of personal data by any court or tribunal or any other body in India which is entrusted by law with the performance of any judicial or quasi-judicial or regulatory or supervisory function, where such processing is necessary for the performance of such function; (c) personal data is processed in the interest of prevention, detection, investigation or prosecution of any offence or contravention of any law for the time being in force in India; (d) personal data of Data Principals not within the territory of India is processed pursuant to any contract entered into with any person outside the territory of India by any person based in India; (e) the processing is necessary for a scheme of compromise or arrangement or merger or amalgamation of two or more companies or a reconstruction by way of demerger or otherwise of a company, or transfer of undertaking of one or more company to another company, or involving division of one or more companies, approved by a court or tribunal or other authority competent to do so by any law for the time being in force; and (f) the processing is for the purpose of ascertaining the financial information and assets and liabilities of any person who has defaulted in payment due on account of a loan or advance taken from a financial institution, subject to such processing being in accordance with the provisions regarding disclosure of information or data in any other law for the time being in force.

Explanation.— "default" and "financial institution" have the meanings assigned to them in sub-sections (12) and (14) of section 3 of the Insolvency and Bankruptcy Code, 2016.

(2) The provisions of this Act shall not apply in respect of the processing of personal data — (a) by such instrumentality of the State as the Central Government may notify, in the interests of sovereignty and integrity of India, security of the State, friendly relations with foreign States, maintenance of public order or preventing incitement to any cognizable offence relating to any of these, and the processing by the Central Government of any personal data that such instrumentality may furnish to it; and (b) necessary for research, archiving or statistical purposes if the personal data is not to be used to take any decision specific to a Data Principal and such processing is carried on in accordance with such standards as may be prescribed.

(3) The Central Government may, having regard to the volume and nature of personal data processed, notify certain Data Fiduciaries or class of Data Fiduciaries, including startups, as Data Fiduciaries to whom the provisions of section 5, sub-sections (3) and (7) of section 8 and sections 10 and 11 shall not apply.

Explanation.— "startup" means a private limited company, partnership firm or limited liability partnership incorporated in India that is eligible to be, and is recognised as, a startup under the criteria and process notified by the department responsible for startups in the Central Government.

(4) In respect of processing by the State or any instrumentality of the State, the provisions of sub-section (7) of section 8 and sub-section (3) of section 12 and, where such processing is for a purpose that does not include making of a decision that affects the Data Principal, sub-section (2) of section 12 shall not apply.

(5) The Central Government may, before expiry of five years from the date of commencement of this Act, by notification, declare that any provision of this Act shall not apply to such Data Fiduciary or classes of Data Fiduciaries for such period as may be specified in the notification.""",
    "Sets broad exemptions from most of the Act's obligations — for legal-right enforcement, judicial/regulatory processing, crime prevention/investigation, foreign-contract processing of non-Indian data, M&A restructuring, and defaulter financial-information processing — plus a notified security-instrumentality exemption, a self-executing research/archiving/statistical exemption, notified exemptions for specific Data Fiduciaries (including startups) from listed sections, a conditional State-processing exemption from parts of Sections 8 and 12, and a five-year sunset power to exempt any Data Fiduciary from any provision by notification.",
)

CORRECTIONS["DPDPA-S28"] = (
"""**Section 28 — Procedure to be followed by Board**

(1) The Board shall function as an independent body and shall, as far as practicable, function as a digital office, with the receipt of complaints and the allocation, hearing and pronouncement of decisions in respect of the same being digital by design, and adopt such techno-legal measures as may be prescribed.

(2) The Board may, on receipt of an intimation or complaint or reference or directions as referred to in sub-section (1) of section 27, take action in accordance with the provisions of this Act and the rules made thereunder.

(3) The Board shall determine whether there are sufficient grounds to proceed with an inquiry.

(4) In case the Board determines that there are insufficient grounds, it may, for reasons to be recorded in writing, close the proceedings.

(5) In case the Board determines that there are sufficient grounds to proceed with inquiry, it may, for reasons to be recorded in writing, inquire into the affairs of any person for ascertaining whether such person is complying with or has complied with the provisions of this Act.

(6) The Board shall conduct such inquiry following the principles of natural justice and shall record reasons for its actions during the course of such inquiry.

(7) For the purposes of discharging its functions under this Act, the Board shall have the same powers as are vested in a civil court under the Code of Civil Procedure, 1908, in respect of matters relating to — (a) summoning and enforcing the attendance of any person and examining her on oath; (b) receiving evidence of affidavit requiring the discovery and production of documents; (c) inspecting any data, book, document, register, books of account or any other document; and (d) such other matters as may be prescribed.

(8) The Board or its officers shall not prevent access to any premises or take into custody any equipment or any item that may adversely affect the day-to-day functioning of a person.

(9) The Board may require the services of any police officer or any officer of the Central Government or a State Government to assist it for the purposes of this section and it shall be the duty of every such officer to comply with such requisition.

(10) During the course of the inquiry, if the Board considers it necessary, it may for reasons to be recorded in writing, issue interim orders after giving the person concerned an opportunity of being heard.

(11) On completion of the inquiry and after giving the person concerned an opportunity of being heard, the Board may for reasons to be recorded in writing, either close the proceedings or proceed in accordance with section 33.

(12) At any stage after receipt of a complaint, if the Board is of the opinion that the complaint is false or frivolous, it may issue a warning or impose costs on the complainant.""",
    None,
)

CORRECTIONS["DPDPA-S42"] = (
"""**Section 42 — Power to amend Schedule**

(1) The Central Government may, by notification, amend the Schedule, subject to the restriction that no such notification shall have the effect of increasing any penalty specified therein to more than twice of what was specified in it when this Act was originally enacted.

(2) Any amendment notified under sub-section (1) shall have effect as if enacted in this Act and shall come into force on the date of the notification.""",
    None,
)

CORRECTIONS["DPDPA-S44.1_3"] = (
"""**Section 44(1),(3) — Amendments to certain Acts**

(1) In section 14 of the Telecom Regulatory Authority of India Act, 1997, in clause (c), for sub-clauses (i) and (ii), the following sub-clauses shall be substituted, namely — "(i) the Appellate Tribunal under the Information Technology Act, 2000; (ii) the Appellate Tribunal under the Airports Economic Regulatory Authority of India Act, 2008; and (iii) the Appellate Tribunal under the Digital Personal Data Protection Act, 2023.".

(3) In section 8 of the Right to Information Act, 2005, in sub-section (1), for clause (j), the following clause shall be substituted, namely — "(j) information which relates to personal information;".""",
    "Amends the TRAI Act, 1997 to replace its Appellate Tribunal list with the IT Act, Airports Economic Regulatory Authority Act, and DPDP Act Appellate Tribunals, and amends the RTI Act, 2005 to add a standalone exemption for 'information which relates to personal information'.",
)

CORRECTIONS["DPDPA-S44.2"] = (
"""**Section 44(2) — Amendments to the Information Technology Act, 2000**

The Information Technology Act, 2000 shall be amended in the following manner, namely — (a) section 43A shall be omitted; (b) in section 81, in the proviso, after the words and figures "the Patents Act, 1970", the words and figures "or the Digital Personal Data Protection Act, 2023" shall be inserted; and (c) in section 87, in sub-section (2), clause (ob) shall be omitted.""",
    "Amends the Information Technology Act, 2000 — removes the old compensation-for-data-breach provision (Section 43A, since this Act now governs that), inserts a cross-reference to this Act into Section 81's proviso, and omits a now-redundant RTI-exemption clause (Section 87(2)(ob)).",
)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON;")

cur = conn.execute("SELECT change_id FROM change_log WHERE change_id LIKE 'CHG-%'")
max_n = 0
for row in cur.fetchall():
    try:
        n = int(row["change_id"].split("-")[-1])
        max_n = max(max_n, n)
    except (ValueError, IndexError):
        continue

applied = []
for pid, (new_full_text, new_summary) in CORRECTIONS.items():
    old = conn.execute(
        "SELECT full_text, current_summary, notes FROM provisions WHERE provision_id = ?", (pid,)
    ).fetchone()
    if old is None:
        raise SystemExit(f"ERROR: {pid} not found in provisions table")
    old_full_text = old["full_text"]
    old_summary = old["current_summary"]
    new_notes = (old["notes"] or "") + CORRECTION_NOTE

    set_clauses = ["full_text = ?", "last_updated_date = ?", "notes = ?"]
    params = [new_full_text, TODAY, new_notes]
    if new_summary is not None:
        set_clauses.append("current_summary = ?")
        params.append(new_summary)
    params.append(pid)

    conn.execute(
        f"UPDATE provisions SET {', '.join(set_clauses)} WHERE provision_id = ?",
        params,
    )

    max_n += 1
    change_id = f"CHG-{max_n:04d}"
    conn.execute(
        """INSERT INTO change_log
           (change_id, detected_timestamp, provision_id, change_type,
            old_value_summary, new_value_summary, old_full_text, new_full_text,
            source_document, source_url, detected_by, confidence_score,
            review_status, applied_to_master, notes)
           VALUES (?, ?, ?, 'Correction', ?, ?, ?, ?, ?, ?, ?, ?, 'Pending Review', 'Y', ?)""",
        (
            change_id,
            f"{TODAY}T01:45:00",
            pid,
            old_summary,
            new_summary if new_summary is not None else old_summary,
            old_full_text,
            new_full_text,
            "Digital Personal Data Protection Act, 2023 (Act No. 22 of 2023)",
            "https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf",
            "cowork:claude-sonnet-5 + claude-opus (manual re-verification against official PDF)",
            0.9,
            "One-time manual data-quality correction (not a detected regulatory "
            "change): DB text diverged from the enacted Act at seeding time. "
            "Corrected against a freshly downloaded, hash-verified copy of the "
            "official PDF, re-verified against a hash-confirmed copy of the "
            "source PDF via a second, independent extraction pass and a second "
            "review pass. review_status left 'Pending Review' since no human "
            "has read the literal corrected text line-by-line yet — see "
            "docs/act_table_audit_2026-09-23.md.",
        ),
    )
    applied.append((pid, change_id))

conn.commit()

print("Applied corrections:")
for pid, cid in applied:
    print(f"  {pid} -> {cid}")

print("\nVerification (re-read from DB):")
for pid, _ in applied:
    row = conn.execute(
        "SELECT full_text, current_summary, last_updated_date FROM provisions WHERE provision_id = ?", (pid,)
    ).fetchone()
    print(f"--- {pid} (last_updated_date={row['last_updated_date']}) ---")
    print(row["full_text"][:150].replace(chr(10), " "), "...")

conn.close()
print("\nDone.")
