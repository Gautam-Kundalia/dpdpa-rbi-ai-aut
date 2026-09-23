"""
Seed db/dpdpa.db with the full DPDP Rules, 2025 — all 23 rules + 7 schedules.

Source: Gazette of India, Extraordinary, Part II, Section 3(i), Notification
G.S.R. 846(E), dated 13 November 2025, Ministry of Electronics and
Information Technology. Fetched directly from the official PDF:
https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf

The full_text field inside each PROVISIONS tuple below is now VESTIGIAL —
kept in place for readability/diff history, but not actually used at seed
time. It predates the 23 Sep 2026 audit fixes (Phase 4a's G.S.R. 892(E)
corrigendum, Phase 4b's Schedule restoration), which were applied as
one-off corrections directly to db/dpdpa.db rather than by retyping this
file (this project's own ground rule: legal text is only ever extracted
by code from an official PDF, never hand-typed). main() instead loads
full_text from data/rules_verbatim_2026-09-23.json — a code-generated
dump of the database's own, already-verified text (see
tests/test_legal_text_verbatim.py) — the same pattern
seed_dpdp_act_full.py uses for the Act table. If this file's own
full_text strings and the JSON ever disagree, the JSON wins; treat the
tuples' full_text as historical reference only.

full_text uses a light markdown convention (**bold** for emphasis,
blank-line-separated paragraphs, '|'-delimited tables) that
src/export_word.py renders into proper Word formatting.

Usage:
    python src/init_db.py                 # schema only, if not already done
    python src/seed_dpdp_rules_full.py
    python src/export_word.py
    python src/export_excel.py
"""
from __future__ import annotations

import json
import re

from db import PROJECT_ROOT, get_connection, init_schema

VERBATIM_JSON_PATH = PROJECT_ROOT / "data" / "rules_verbatim_2026-09-23.json"


def load_verbatim_full_text() -> dict[str, str]:
    """provision_id -> full_text, code-dumped from the database's own
    already-verified text (see VERBATIM_JSON_PATH's own 'meta' key)."""
    data = json.loads(VERBATIM_JSON_PATH.read_text(encoding="utf-8"))
    return {pid: entry["full_text"] for pid, entry in data["provisions"].items()}

SOURCE_DOC = "DPDP Rules, 2025 — Gazette Notification G.S.R. 846(E), 13 Nov 2025"
SOURCE_URL = "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf"
FETCHED_DATE = "2026-08-31"
DOCX_PATH = "docs/DPDP_Rules_2025.docx"

EFF_GROUP_A = ("2025-11-13", "In force from date of Gazette publication (Rule 1(2)).")
EFF_GROUP_B = ("2026-11-13", "In force one year after Gazette publication (Rule 1(3)).")
EFF_GROUP_C = ("2027-05-13", "In force eighteen months after Gazette publication (Rule 1(4)) — not yet operative.")

# (provision_id, reference, topic, summary, effective_group, full_text)
PROVISIONS = [
    ("DPDPR-R1", "Rule 1", "Other",
     "Short title (Digital Personal Data Protection Rules, 2025) and staggered commencement schedule for different rules.",
     EFF_GROUP_A,
     "**Rule 1 — Short title and commencement**\n\n"
     "(1) These rules may be called the Digital Personal Data Protection Rules, 2025.\n\n"
     "(2) Rules 1, 2 and 17 to 21 shall come into force on the date of their publication in the Official Gazette.\n\n"
     "(3) Rule 4 shall come into force one year after the date of publication of this Gazette.\n\n"
     "(4) Rules 3, 5 to 16, 22 and 23 shall come into force eighteen months after the date of publication of this Gazette."),

    ("DPDPR-R2", "Rule 2", "Definitions",
     "Defines 'Act', 'techno-legal measures', 'user account', and 'verifiable consent' for purposes of the Rules; undefined terms take their meaning from the Act.",
     EFF_GROUP_A,
     "**Rule 2 — Definitions**\n\n"
     "(1) In these rules, unless the context otherwise requires, —\n\n"
     "(a) \"Act\" means the Digital Personal Data Protection Act, 2023 (22 of 2023);\n\n"
     "(b) \"techno-legal measures\" means as referred to under rules 20 and 22;\n\n"
     "(c) \"user account\" means the online account registered by the Data Principal with the Data Fiduciary, "
     "and includes any profiles, pages, handles, email address, mobile number and other similar presences by "
     "means of which such Data Principal is able to access the services of such Data Fiduciary; and\n\n"
     "(d) \"verifiable consent\" means a consent as specified in rule 10 or 11.\n\n"
     "(2) The words and expressions used in these rules and not defined, but defined in the Act, shall have "
     "the same meanings respectively assigned to them in the Act."),

    ("DPDPR-R3", "Rule 3", "Consent & Notice",
     "Sets the content requirements for the notice a Data Fiduciary must give a Data Principal before processing — itemised data description, purpose, and links to withdraw consent, exercise rights, or complain to the Board.",
     EFF_GROUP_C,
     "**Rule 3 — Notice given by Data Fiduciary to Data Principal**\n\n"
     "The notice given by the Data Fiduciary to the Data Principal shall —\n\n"
     "(a) be presented and be understandable independently of any other information that has been, is or may "
     "be made available by such Data Fiduciary;\n\n"
     "(b) give, in clear and plain language, a fair account of the details necessary to enable the Data "
     "Principal to give specific and informed consent for the processing of her personal data, which shall "
     "include, at the minimum, —\n"
     "(i) an itemised description of such personal data; and\n"
     "(ii) the specified purpose or purposes of, and specific description of the goods or services to be "
     "provided or uses to be enabled by, such processing; and\n\n"
     "(c) give, the particular communication link for accessing the website or app, or both, of such Data "
     "Fiduciary, and a description of other means, if any, using which such Data Principal may —\n"
     "(i) withdraw her consent, with the ease of doing so being comparable to that with which such consent "
     "was given;\n"
     "(ii) exercise her rights under the Act; and\n"
     "(iii) make a complaint to the Board."),

    ("DPDPR-R4", "Rule 4", "Consent Manager",
     "Sets the process for a company to register as a Consent Manager with the Board, and the Board's powers to reject, suspend, or cancel that registration for non-adherence.",
     EFF_GROUP_B,
     "**Rule 4 — Registration and obligations of Consent Manager**\n\n"
     "(1) A person who fulfils the conditions for registration of Consent Managers set out in Part A of First "
     "Schedule may apply to the Board for registration as a Consent Manager by furnishing such particulars and "
     "such other information and documents as the Board may publish in this behalf on its website.\n\n"
     "(2) On receipt of such application, the Board may make such inquiry as it may deem fit to satisfy itself "
     "regarding fulfilment of the conditions set out in Part A of First Schedule, and if it —\n"
     "(a) is satisfied, register the applicant as a Consent Manager, under intimation to the applicant, and "
     "publish on its website the particulars of such Consent Manager; or\n"
     "(b) is not satisfied, reject the application and communicate the reasons for the rejection to the "
     "applicant.\n\n"
     "(3) The Consent Manager shall have obligations as specified in Part B of First Schedule.\n\n"
     "(4) If the Board is of the opinion that a Consent Manager is not adhering to the conditions and "
     "obligations under this rule, it may, after giving an opportunity of being heard, inform the Consent "
     "Manager of such non-adherence and direct the Consent Manager to take measures to ensure adherence.\n\n"
     "(5) The Board may, if it is satisfied that it is necessary so to do in the interests of Data Principals, "
     "after giving the Consent Manager an opportunity of being heard, by order, for reasons to be recorded in "
     "writing, —\n"
     "(a) suspend or cancel the registration of such Consent Manager; and\n"
     "(b) give such directions as it may deem fit to that Consent Manager, to protect the interests of the "
     "Data Principals.\n\n"
     "(6) The Board may, for the purposes of this rule, require the Consent Manager to furnish such "
     "information as the Board may call for."),

    ("DPDPR-R5", "Rule 5", "Other",
     "Governs processing of personal data by the State and its instrumentalities to provide or issue subsidies, benefits, services, certificates, licences or permits — must follow the Second Schedule standards.",
     EFF_GROUP_C,
     "**Rule 5 — Processing of personal data for provision or issue of subsidy, benefit, service, certificate, "
     "licence or permit by State and its instrumentalities**\n\n"
     "(1) Processing the personal data of a Data Principal under this rule shall be done following the "
     "standards specified in Second Schedule.\n\n"
     "(2) In this rule and the Second Schedule, the reference to any subsidy, benefit, service, certificate, "
     "licence or permit that is provided or issued —\n\n"
     "(a) under law shall be construed as a reference to provision or issuance of such subsidy, benefit, "
     "service, certificate, licence or permit in exercise of any power of or the performance of any function "
     "by the State or any of its instrumentalities under any law for the time being in force;\n\n"
     "(b) under policy shall be construed as a reference to provision or issuance of such subsidy, benefit, "
     "service, certificate, licence or permit under any policy or instruction issued by the Central Government "
     "or a State Government in exercise of its executive power; and\n\n"
     "(c) using public funds shall be construed as a reference to provision or issuance of such subsidy, "
     "benefit, service, certificate, licence or permit by incurring expenditure on the same from, or with "
     "accrual of receipts to, —\n"
     "(i) in case of the Central Government or a State Government, the Consolidated Fund of India or the "
     "Consolidated Fund of the State or the public account of India or the public account of the State; or\n"
     "(ii) in case of any local or other authority within the territory of India or under the control of the "
     "Government of India or of any State, the fund or funds of such authority."),

    ("DPDPR-R6", "Rule 6", "Other",
     "Requires Data Fiduciaries to implement minimum 'reasonable security safeguards' — encryption/masking, access controls, logging & monitoring, continuity measures, contractual safeguards with processors, and one-year retention of security logs.",
     EFF_GROUP_C,
     "**Rule 6 — Reasonable security safeguards**\n\n"
     "(1) A Data Fiduciary shall protect personal data in its possession or under its control, including in "
     "respect of any processing undertaken by it or on its behalf by a Data Processor, by taking reasonable "
     "security safeguards to prevent personal data breach, which shall include, at the minimum, —\n\n"
     "(a) appropriate data security measures, such as securing of personal data through encryption, "
     "obfuscation, masking or the use of virtual tokens mapped to that personal data;\n\n"
     "(b) appropriate measures to control access to the computer resources used by such Data Fiduciary or "
     "such a Data Processor, wherever applicable;\n\n"
     "(c) visibility on the accessing of such personal data, through appropriate logs, monitoring and review, "
     "for enabling detection of unauthorised access, its investigation and remediation to prevent recurrence;\n\n"
     "(d) reasonable measures for continued processing in the event of confidentiality, integrity or "
     "availability of such personal data being compromised as a result of destruction or loss of access to "
     "personal data or otherwise, such as by way of data-backups;\n\n"
     "(e) for enabling the detection of unauthorised access, its investigation, remediation to prevent "
     "recurrence and continued processing in the event of such a compromise, retain such logs and personal "
     "data for a period of one year, unless compliance with any law for the time being in force requires "
     "otherwise;\n\n"
     "(f) appropriate provision in the contract entered into between such Data Fiduciary and such a Data "
     "Processor, wherever applicable, for taking reasonable security safeguards; and\n\n"
     "(g) appropriate technical and organisational measures to ensure effective observance of security "
     "safeguards.\n\n"
     "(2) In this rule, the expression \"computer resource\" shall have the same meaning as is assigned to it "
     "in Information Technology Act, 2000 (21 of 2000)."),

    ("DPDPR-R7", "Rule 7", "Breach Notification",
     "Sets breach-notification obligations: Data Fiduciary must inform each affected Data Principal without delay, and must inform the Board without delay initially, then with a detailed report within 72 hours (or a Board-extended period).",
     EFF_GROUP_C,
     "**Rule 7 — Intimation of personal data breach**\n\n"
     "(1) On becoming aware of any personal data breach, the Data Fiduciary shall, to the best of its "
     "knowledge, intimate to each affected Data Principal, in a concise, clear and plain manner and without "
     "delay, through her user account or any mode of communication registered by her with the Data Fiduciary, "
     "—\n\n"
     "(a) a description of the breach, including its nature, extent and the timing of its occurrence;\n\n"
     "(b) the consequences relevant to her, that are likely to arise from the breach;\n\n"
     "(c) the measures implemented and being implemented by the Data Fiduciary, if any, to mitigate risk;\n\n"
     "(d) the safety measures that she may take to protect her interests; and\n\n"
     "(e) business contact information of a person who is able to respond on behalf of the Data Fiduciary, to "
     "queries, if any, of the Data Principal.\n\n"
     "(2) On becoming aware of any personal data breach, the Data Fiduciary shall intimate to the Board, —\n\n"
     "(a) without delay, a description of the breach, including its nature, extent, timing and location of "
     "occurrence and the likely impact;\n\n"
     "(b) within seventy-two hours of becoming aware of the breach, or within such longer period as the Board "
     "may allow on a request made in writing in this behalf, —\n"
     "(i) updated and detailed information in respect of such description;\n"
     "(ii) the broad facts related to the events, circumstances and reasons leading to the breach;\n"
     "(iii) measures implemented or proposed, if any, to mitigate risk;\n"
     "(iv) any findings regarding the person who caused the breach;\n"
     "(v) remedial measures taken to prevent recurrence of such breach; and\n"
     "(vi) a report regarding the intimations given to affected Data Principals."),

    ("DPDPR-R8.1_2", "Rule 8(1)-(2)", "Retention & Erasure",
     "For specified classes of Data Fiduciary (e-commerce, online gaming, social media intermediaries above user thresholds — see Third Schedule), personal data must be erased once the specified purpose is deemed no longer served, with 48-hour advance notice to the Data Principal before erasure.",
     EFF_GROUP_C,
     "**Rule 8(1)-(2) — Time period for specified purpose to be deemed as no longer being served**\n\n"
     "(1) A Data Fiduciary, who is of such class and is processing personal data for such corresponding "
     "purposes as are specified in Third Schedule, shall erase such personal data, unless its retention is "
     "necessary for compliance with any law for the time being in force, or, for the corresponding time period "
     "specified in the Third Schedule, if the Data Principal neither approaches such Data Fiduciary for the "
     "performance of the specified purpose nor exercises her rights in relation to such processing.\n\n"
     "(2) At least forty-eight hours before completion of the time period for erasure of personal data under "
     "this rule, the Data Fiduciary shall inform the Data Principal that such personal data shall be erased "
     "upon completion of such period, unless she logs into her user account or otherwise initiates contact "
     "with the Data Fiduciary for the performance of the specified purpose or exercises her rights in relation "
     "to the processing of such personal data."),

    ("DPDPR-R8.3", "Rule 8(3)", "Retention & Erasure",
     "Data Fiduciary must retain personal data, related traffic data, and processing logs for a minimum of one year from date of processing (per the Seventh Schedule purposes), then erase — unless a longer period is legally required.",
     EFF_GROUP_C,
     "**Rule 8(3) — Retention of processing logs**\n\n"
     "Without prejudice to sub-rules (1) and (2), a Data Fiduciary shall retain, in respect of any processing "
     "of personal data undertaken by it or on its behalf by a Data Processor, such personal data, associated "
     "traffic data and other logs of the processing for a minimum period of one year from the date of such "
     "processing, for the purposes as specified in the Seventh Schedule, after which the Data Fiduciary shall "
     "cause such personal data and logs to be erased, unless further retention is required for compliance "
     "with any other law for the time being in force or notified by the Government.\n\n"
     "**Illustration.**\n\n"
     "Case 1: X, a Data Principal purchases an e-book on an e-book platform Y. Once delivery is completed, the "
     "specified purpose of processing is served. The platform Y must retain the order details, personal data, "
     "and logs of the processing (such as order confirmation, payment, and delivery events) for at least one "
     "year from the date of the transaction, even if X deletes her account.\n\n"
     "Case 2: X, a company engages a cloud service provider C as its Data Processor to host customer records. "
     "X as the Data Fiduciary, is required to ensure that the C also retains the data and associated logs for "
     "at least one year before erasure, unless any other applicable law requires a longer period."),

    ("DPDPR-R9", "Rule 9", "Data Principal Rights",
     "Every Data Fiduciary must prominently publish the contact information of its Data Protection Officer (or an equivalent contact) able to answer questions about personal data processing.",
     EFF_GROUP_C,
     "**Rule 9 — Contact information of person to answer questions about processing**\n\n"
     "Every Data Fiduciary shall prominently publish on its website or app, and mention in every response to a "
     "communication for the exercise of the rights of a Data Principal under the Act, the business contact "
     "information of the Data Protection Officer, if applicable, or a person who is able to answer on behalf "
     "of the Data Fiduciary the questions of the Data Principal about the processing of her personal data."),

    ("DPDPR-R10", "Rule 10", "Children & Persons with Disabilities",
     "Sets due-diligence requirements for obtaining verifiable parental consent before processing a child's personal data — via reliable identity/age details or a virtual token from an authorised entity (including Digital Locker providers). Includes four worked illustrations.",
     EFF_GROUP_C,
     "**Rule 10 — Verifiable consent for processing of personal data of child**\n\n"
     "(1) A Data Fiduciary shall adopt appropriate technical and organisational measures to ensure that "
     "verifiable consent of the parent is obtained before the processing of any personal data of a child and "
     "shall observe due diligence, for checking that the individual identifying herself as the parent is an "
     "adult who is identifiable if required in connection with compliance with any law for the time being in "
     "force in India, by reference to —\n\n"
     "(a) reliable details of identity and age of the individual available with the Data Fiduciary; or\n\n"
     "(b) details of identity and age, voluntarily provided —\n"
     "(i) by the individual; or\n"
     "(ii) through a virtual token mapped to such details, which is issued by an authorised entity.\n\n"
     "(2) In this rule, the expression —\n\n"
     "(a) \"adult\" shall mean an individual who has completed the age of eighteen years;\n\n"
     "(b) \"authorised entity\" shall mean —\n"
     "(i) an entity entrusted by law or by the Central Government or by the State Government with the "
     "issuance of details of the identity and age or a virtual token mapped to such details; or\n"
     "(ii) a person appointed or permitted by the entity specified under clause (i), for such issuance, and "
     "also includes details of identity and age or token made available and verified by a Digital Locker "
     "Service Provider;\n\n"
     "(c) \"Digital Locker service provider\" shall mean such intermediary, including a body corporate or an "
     "agency of the appropriate Government, as may be notified by the Central Government, in accordance with "
     "the rules made in this regard under the Information Technology Act, 2000 (21 of 2000).\n\n"
     "**Illustration.**\n\n"
     "C is a child, P is a parent, and DF is a Data Fiduciary. A user account of C is sought to be created on "
     "the online platform of DF, by processing the personal data of C.\n\n"
     "Case 1: C informs DF that she is a child and declares P as her parent. DF shall enable P to identify "
     "herself through its website, app or other appropriate means. P identifies herself as the parent and "
     "informs DF that she is a registered user on DF's platform and has previously made available her identity "
     "and age details to DF. Before processing C's personal data for the creation of her user account, DF "
     "shall check to confirm that it holds reliable identity and age details of P and that P is an "
     "identifiable adult.\n\n"
     "Case 2: C informs DF that she is a child and declares P as her parent. DF shall enable P to identify "
     "herself through its website, app or other appropriate means. P identifies herself as the parent and "
     "informs DF that she herself is not a registered user on DF's platform. Before processing C's personal "
     "data for the creation of her user account, DF shall, by reference to identity and age details issued by "
     "an entity entrusted by law or the Government with maintenance of the said details or to a virtual token "
     "mapped to the identity and age, check that P is an identifiable adult. P may voluntarily make such "
     "details available using the services of a Digital Locker service provider.\n\n"
     "Case 3: P is opening an account for C and identifies herself as C's parent and informs DF that she is a "
     "registered user on DF's platform and has previously made available her identity and age details to DF. "
     "Before processing C's personal data for the creation of her user account, DF shall check to confirm that "
     "it holds reliable identity and age details of P and that P is an identifiable adult.\n\n"
     "Case 4: P is opening an account for C and identifies herself as C's parent and informs DF that she "
     "herself is not a registered user on DF's platform. Before processing C's personal data for the creation "
     "of her user account, DF shall, by reference to identity and age details issued by an entity entrusted by "
     "law or the Government with maintenance of the said details or to a virtual token mapped to the identity "
     "and age, check that P is an identifiable adult. P may voluntarily make such details available using the "
     "services of a Digital Locker service provider."),

    ("DPDPR-R11", "Rule 11", "Children & Persons with Disabilities",
     "Sets due-diligence requirements for verifying that someone claiming to be the lawful guardian of a person with disability is genuinely court/authority-appointed, before relying on their consent.",
     EFF_GROUP_C,
     "**Rule 11 — Verifiable consent for processing of personal data of person with disability who has lawful "
     "guardian**\n\n"
     "(1) A Data Fiduciary, while obtaining verifiable consent from an individual identifying herself as the "
     "lawful guardian of a person with disability, shall observe due diligence to verify that such guardian is "
     "appointed by a court of law, or by a designated authority or by a local level committee, under the law "
     "applicable to guardianship.\n\n"
     "(2) In this rule, the expression —\n\n"
     "(a) \"designated authority\" shall mean an authority designated under section 15 of the Rights of "
     "Persons with Disabilities Act, 2016 (49 of 2016) to support persons with disabilities in exercise of "
     "their legal capacity;\n\n"
     "(b) \"law applicable to guardianship\" shall mean, —\n"
     "(i) in relation to an individual who has long term physical, mental, intellectual or sensory impairment "
     "which, in interaction with barriers, hinders her full and effective participation in society equally "
     "with others and who despite being provided adequate and appropriate support is unable to take legally "
     "binding decisions, the provisions of law contained in Rights of Persons with Disabilities Act, 2016 "
     "(49 of 2016) and the rules made thereunder; and\n"
     "(ii) in relation to a person who is suffering from any of the conditions relating to autism, cerebral "
     "palsy, mental retardation or a combination of such conditions and includes a person suffering from "
     "severe multiple disability, the provisions of law of the National Trust for the Welfare of Persons with "
     "Autism, Cerebral Palsy, Mental Retardation and Multiple Disabilities Act, 1999 (44 of 1999) and the "
     "rules made thereunder;\n\n"
     "(c) \"local level committee\" shall mean a local level committee constituted under section 13 of the "
     "National Trust for the Welfare of Persons with Autism, Cerebral Palsy, Mental Retardation and Multiple "
     "Disabilities Act, 1999 (44 of 1999);\n\n"
     "(d) \"person with disability\" shall mean and include —\n"
     "(i) an individual who has long term physical, mental, intellectual or sensory impairment which, in "
     "interaction with barriers, hinders her full and effective participation in society equally with others "
     "and who, despite being provided adequate and appropriate support, is unable to take legally binding "
     "decisions; and\n"
     "(ii) an individual who is suffering from any of the conditions relating to autism, cerebral palsy, "
     "mental retardation or a combination of any two or more of such conditions and includes an individual "
     "suffering from severe multiple disability and who, despite being provided adequate and appropriate "
     "support, is unable to take legally binding decisions."),

    ("DPDPR-R12", "Rule 12", "Children & Persons with Disabilities",
     "Exempts specified classes of Data Fiduciary (healthcare providers, educational institutions, crèches, child transport providers — Fourth Schedule Part A) and specified purposes (Part B, e.g. safety tracking, email accounts) from the Act's general prohibition on tracking/behavioural monitoring/targeted ads directed at children.",
     EFF_GROUP_C,
     "**Rule 12 — Exemptions from certain obligations applicable to processing of personal data of child**\n\n"
     "(1) The provisions of sub-sections (1) and (3) of section 9 of the Act shall not be applicable to "
     "processing of personal data of a child by such class of Data Fiduciaries as are specified in Part A of "
     "Fourth Schedule, subject to such conditions as are specified in the said Part.\n\n"
     "(2) The provisions of sub-sections (1) and (3) of section 9 of the Act shall not be applicable to "
     "processing of personal data of a child for such purposes as are specified in Part B of Fourth Schedule, "
     "subject to such conditions as are specified in the said Part."),

    ("DPDPR-SDF-R13", "Rule 13", "Significant Data Fiduciary",
     "Significant Data Fiduciaries must conduct an annual Data Protection Impact Assessment and audit, verify their algorithmic/technical systems don't risk Data Principals' rights, and comply with any government restriction on transferring specified personal data outside India.",
     EFF_GROUP_C,
     "**Rule 13 — Additional obligations of Significant Data Fiduciary**\n\n"
     "(1) A Significant Data Fiduciary shall, once in every period of twelve months from the date on which it "
     "is notified as such or is included in the class of Data Fiduciaries notified as such, undertake a Data "
     "Protection Impact Assessment and an audit to ensure effective observance of the provisions of this Act "
     "and the rules made thereunder.\n\n"
     "(2) A Significant Data Fiduciary shall cause the person carrying out the Data Protection Impact "
     "Assessment and audit to furnish to the Board a report containing significant observations in the Data "
     "Protection Impact Assessment and audit.\n\n"
     "(3) A Significant Data Fiduciary shall observe due diligence to verify that technical measures including "
     "algorithmic software adopted by it for hosting, display, uploading, modification, publishing, "
     "transmission, storage, updating or sharing of personal data processed by it are not likely to pose a "
     "risk to the rights of Data Principals.\n\n"
     "(4) A Significant Data Fiduciary shall undertake measures to ensure that personal data specified by the "
     "Central Government, on the basis of the recommendations of a committee constituted by it, is processed "
     "subject to the restriction that the personal data and the traffic data pertaining to its flow is not "
     "transferred outside the territory of India.\n\n"
     "(5) In this rule, \"committee\" means a committee constituted by the Central Government for the purpose "
     "of this rule, which shall include officials from the Ministry of Electronics and Technology and may "
     "include officials from other Ministries or Department of the Central Government."),

    ("DPDPR-R14", "Rule 14", "Data Principal Rights",
     "Requires Data Fiduciaries and Consent Managers to publish the means for exercising Data Principal rights, respond to grievances within 90 days via an effective grievance system, and allows nominating individuals to exercise rights on the Data Principal's behalf.",
     EFF_GROUP_C,
     "**Rule 14 — Rights of Data Principals**\n\n"
     "(1) For enabling Data Principals to exercise their rights under the Act, the Data Fiduciary and, where "
     "applicable, the Consent Manager, shall prominently publish on its website or app, or both, as the case "
     "may be, —\n\n"
     "(a) the details of the means using which a Data Principal may make a request for the exercise of such "
     "rights; and\n\n"
     "(b) the particulars, if any, such as the username or other identifier of such a Data Principal, which "
     "may be required to identify her under its terms of service.\n\n"
     "(2) To exercise the rights of the Data Principal under the Act, she may make a request to the Data "
     "Fiduciary to whom she has previously given consent for processing of her personal data, using the means "
     "and furnishing the particulars required by such Data Fiduciary for the exercise of such rights.\n\n"
     "(3) Every Data Fiduciary and Consent Manager shall prominently publish on its website or app, or both, "
     "as the case may be, within a reasonable period not exceeding ninety days under its grievance redressal "
     "system for responding to the grievances of Data Principals and shall, for ensuring the effectiveness of "
     "the system in responding within such period, implement appropriate technical and organisational "
     "measures.\n\n"
     "(4) To exercise the rights of the Data Principal under the Act, she may, in accordance with the terms of "
     "service of the Data Fiduciary and such law as may be applicable, nominate one or more individuals, using "
     "the means and furnishing the particulars required by such Data Fiduciary for the exercise of such "
     "right.\n\n"
     "(5) In this rule, the expression \"identifier\" shall mean any sequence of characters issued by the Data "
     "Fiduciary to identify the Data Principal and includes a customer identification file number, customer "
     "acquisition form number, application reference number, enrolment ID, email address, mobile number or "
     "licence number that enables such identification."),

    ("DPDPR-R15", "Rule 15", "Cross-Border Transfer",
     "Permits transferring personal data outside India, subject to the Data Fiduciary meeting requirements the Central Government may specify for making data available to a foreign State or entities under its control.",
     EFF_GROUP_C,
     "**Rule 15 — Transfer of personal data outside the territory of India**\n\n"
     "Any personal data processed by a Data Fiduciary under the Act may be transferred outside the territory "
     "of India subject to the restriction that the Data Fiduciary shall meet such requirements as the Central "
     "Government may, by general or special order, specify in respect of making such personal data available "
     "to any foreign State, or to any person or entity under the control of or any agency of such a State."),

    ("DPDPR-R16", "Rule 16", "Exemptions",
     "Exempts personal data processing necessary for research, archiving, or statistical purposes from the Act, provided it follows the Second Schedule standards.",
     EFF_GROUP_C,
     "**Rule 16 — Exemption from Act for research, archiving or statistical purposes**\n\n"
     "The provisions of the Act shall not apply to the processing of personal data necessary for research, "
     "archiving or statistical purposes if it is carried on in accordance with the standards specified in "
     "Second Schedule."),

    ("DPDPR-R17", "Rule 17", "Data Protection Board",
     "Sets up Search-cum-Selection Committees to recommend appointees to the Data Protection Board — one for the Chairperson, one for other Members.",
     EFF_GROUP_A,
     "**Rule 17 — Appointment of Chairperson and other Members**\n\n"
     "(1) The Central Government shall constitute a Search-cum-Selection Committee, with the Cabinet Secretary "
     "as the chairperson and the Secretaries to the Government of India in charge of the Department of Legal "
     "Affairs and the Ministry of Electronics and Information Technology and two experts of repute having "
     "special knowledge or practical experience in a field which in the opinion of the Central Government may "
     "be useful to the Board as members, to recommend individuals for appointment as Chairperson.\n\n"
     "(2) The Central Government shall constitute a Search-cum-Selection Committee, with the Secretary to the "
     "Government of India in the Ministry of Electronics and Information Technology as the chairperson and the "
     "Secretary to the Government of India in charge of the Department of Legal Affairs, and two experts of "
     "repute having special knowledge or practical experience in a field which in the opinion of the Central "
     "Government may be useful to the Board as members, to recommend individuals for appointment as a Member "
     "other than the Chairperson.\n\n"
     "(3) The Central Government shall, after considering the suitability of individuals recommended by the "
     "Search-cum-Selection Committee, appoint the Chairperson or other Member, as the case may be.\n\n"
     "(4) No act or proceeding of the Search-cum-Selection Committee specified in sub-rules (1) and (2) of "
     "this rule shall be called in question on the ground merely of the existence of any vacancy or absences "
     "in such committee or defect in its constitution."),

    ("DPDPR-R18", "Rule 18", "Data Protection Board",
     "Board Chairperson and Members' salary, allowances, and service conditions are as specified in the Fifth Schedule.",
     EFF_GROUP_A,
     "**Rule 18 — Salary, allowances and other terms and conditions of service of Chairperson and other "
     "Members**\n\n"
     "The Chairperson and every other Member shall receive such salary and allowances and shall have such "
     "other terms and conditions of service as are specified in Fifth Schedule."),

    ("DPDPR-R19", "Rule 19", "Data Protection Board",
     "Sets the Board's meeting procedure — quorum, majority voting with a casting vote, conflict-of-interest recusal, emergency powers, order authentication, and a six-month inquiry deadline.",
     EFF_GROUP_A,
     "**Rule 19 — Procedure for meetings of Board and authentication of its orders, directions and "
     "instruments**\n\n"
     "(1) The Chairperson shall fix the date, time and place of meetings of the Board, approve the items of "
     "agenda therefor, and cause notice specifying the same to be issued under her signature or that of such "
     "other individual as the Chairperson may authorise by general or special order in writing.\n\n"
     "(2) Meetings of the Board shall be chaired by the Chairperson and, in her absence, by such other Member "
     "as the Members present at the meeting may choose from amongst themselves.\n\n"
     "(3) One-third of the membership of the Board shall be the quorum for its meetings.\n\n"
     "(4) All questions which come up before any meeting of the Board shall be decided by a majority of the "
     "votes of Members present and voting, and, in the event of an equality of votes, the Chairperson, or in "
     "her absence, the person chairing, shall have a second or casting vote.\n\n"
     "(5) If a Member has an interest in any item of business to be transacted at a meeting of the Board, she "
     "shall not participate in or vote on the same and, in such a case, the decision on such item shall be "
     "taken by a majority of the votes of other Members present and voting.\n\n"
     "(6) In case an emergent situation warrants immediate action by the Board and it is not feasible to call "
     "a meeting of the Board, the Chairperson may, while recording the reasons in writing, take such action as "
     "may be necessary, which shall be communicated within seven days to all Members and laid before the Board "
     "for ratification at its next meeting.\n\n"
     "(7) If the Chairperson so directs, an item of business or issue which requires decision of the Board may "
     "be referred to Members by circulation and such item may be decided with the approval of majority of the "
     "Members.\n\n"
     "(8) The Chairperson or any Member of the Board, or any individual authorised by it, by a general or "
     "special order in writing, may, under her signature, authenticate its order, direction or instrument.\n\n"
     "(9) The inquiry by the Board shall be completed within a period of six months from the date of receipt "
     "of the intimation, complaint, reference or direction under section 27 of the Act, unless such period is "
     "extended by it, for reasons to be recorded in writing, for a further period not exceeding three months "
     "at a time."),

    ("DPDPR-R20", "Rule 20", "Data Protection Board",
     "The Board functions as a digital office and may use techno-legal measures to conduct proceedings without requiring physical presence, without prejudice to its summoning/examination-on-oath powers.",
     EFF_GROUP_A,
     "**Rule 20 — Functioning of Board as digital office**\n\n"
     "The Board shall function as a digital office, without prejudice to its power to summon and enforce the "
     "attendance of any person and examine her on oath, may adopt techno-legal measures to conduct proceedings "
     "in a manner that does not require physical presence of any individual."),

    ("DPDPR-R21", "Rule 21", "Data Protection Board",
     "The Board may appoint officers/employees (with prior Central Government approval); their service terms are in the Sixth Schedule.",
     EFF_GROUP_A,
     "**Rule 21 — Terms and conditions of appointment and service of officers and employees of Board**\n\n"
     "(1) The Board may, with previous approval of the Central Government, appoint such officers and "
     "employees as it may deem necessary for the efficient discharge of its functions under the provisions of "
     "the Act.\n\n"
     "(2) The terms and conditions of service of officers and employees of the Board shall be such as are "
     "specified in Sixth Schedule."),

    ("DPDPR-R22", "Rule 22", "Data Protection Board",
     "Sets the appeal process to the Appellate Tribunal against a Board order/direction — digital filing, a prescribed fee (waivable), and the Tribunal's freedom from Civil Procedure Code formality, guided instead by natural justice.",
     EFF_GROUP_C,
     "**Rule 22 — Appeal to Appellate Tribunal**\n\n"
     "(1) Any person aggrieved by an order or direction of the Board, may prefer an appeal before the "
     "Appellate Tribunal, it shall be filed in digital form as the Appellate Tribunal may decide.\n\n"
     "(2) An appeal filed with the Appellate Tribunal shall be accompanied by fee of like amount as is "
     "applicable in respect of an appeal filed under the Telecom Regulatory Authority of India Act, 1997 "
     "(24 of 1997), unless reduced or waived by the Chairperson of the Appellate Tribunal at her discretion, "
     "and the same shall be payable digitally using the Unified Payments Interface or such other payment "
     "system authorised by the Reserve Bank of India.\n\n"
     "(3) The Appellate Tribunal —\n"
     "(a) shall not be bound by the procedure laid down by the Code of Civil Procedure, 1908 (5 of 1908), but "
     "shall be guided by the principles of natural justice and, subject to the provisions of the Act, may "
     "regulate its own procedure; and\n"
     "(b) shall function as a digital office which, without prejudice to its power to summon and enforce the "
     "attendance of any person and examine her on oath, may adopt techno-legal measures to conduct proceedings "
     "in a manner that does not require physical presence of any individual."),

    ("DPDPR-R23", "Rule 23", "Other",
     "Empowers the Central Government to require Data Fiduciaries/intermediaries to furnish information for Seventh Schedule purposes, and to restrict disclosure of that request where it could prejudice India's sovereignty/integrity/security.",
     EFF_GROUP_C,
     "**Rule 23 — Calling for information from Data Fiduciary or intermediary**\n\n"
     "(1) The Central Government may, for such purposes of the Act as are specified in Seventh Schedule, "
     "acting through the corresponding authorised person specified in the said Schedule, require any Data "
     "Fiduciary or intermediary to furnish such information as may be called for, within the specified period "
     "as may be given in such.\n\n"
     "(2) Where the disclosure of furnishing of information as referred to in sub-rule (1) is likely to "
     "prejudicially affect the sovereignty and integrity of India or security of the State, the Central "
     "Government may require the Data Fiduciary or intermediary to not disclose such furnishing to affected "
     "Data Principal or any other person except with the previous permission, in writing, of the authorised "
     "person.\n\n"
     "(3) For the purposes of this rule, the expression \"intermediary\" shall have the same meaning as "
     "assigned to it in the Information Technology Act, 2000 (21 of 2000)."),

    ("DPDPR-SCH1", "First Schedule", "Consent Manager",
     "Sets Consent Manager registration conditions (Part A) and ongoing obligations (Part B) in full — Indian incorporation, ₹2 crore net worth, fit-and-proper management, consent-routing blindness, 7-year record retention, conflict-of-interest avoidance, and Board-approval for change of control.",
     EFF_GROUP_B,
     "**First Schedule** *(see rule 4)*\n\n"
     "**PART A — Conditions for registration of Consent Manager**\n\n"
     "1. The applicant is a company incorporated in India.\n\n"
     "2. The applicant has sufficient capacity, including technical, operational and financial capacity, to "
     "fulfil its obligations as a Consent Manager.\n\n"
     "3. The financial condition and the general character of management of the applicant are sound.\n\n"
     "4. The net worth of the applicant is not less than two crore rupees.\n\n"
     "5. The volume of business likely to be available to and the capital structure and earning prospects of "
     "the applicant are adequate.\n\n"
     "6. The directors, key managerial personnel and senior management of the applicant company are "
     "individuals with a general reputation and record of fairness and integrity.\n\n"
     "7. The memorandum of association and articles of association of the applicant company contain "
     "provisions requiring that the obligations under items 9 and 10 of Part B are adhered to, that policies "
     "and procedures are in place to ensure such adherence, and that such provisions may be amended only with "
     "the previous approval of the Board.\n\n"
     "8. The operations proposed to be undertaken by the applicant are in the interests of Data Principals.\n\n"
     "9. It is independently certified that —\n"
     "(a) the interoperable platform of the applicant to enable the Data Principal to give, manage, review and "
     "withdraw her consent is consistent with such data protection standards and assurance framework as may be "
     "published by the Board on its website from time to time; and\n"
     "(b) appropriate technical and organisational measures are in place to ensure adherence to such standards "
     "and framework and effective observance of the obligations under item 11 of Part B.\n\n"
     "**PART B — Obligations of Consent Manager**\n\n"
     "1. The Consent Manager shall enable a Data Principal using its platform to give consent to the "
     "processing of her personal data by a Data Fiduciary onboarded onto such platform either directly to such "
     "Data Fiduciary or through another Data Fiduciary onboarded onto such platform, who maintains such "
     "personal data with the consent of that Data Principal.\n\n"
     "2. The Consent Manager shall ensure that the manner of making available the personal data or its "
     "sharing is such that the contents thereof are not readable by it.\n\n"
     "3. The Consent Manager shall maintain on its platform a record of the following, namely: —\n"
     "(a) Consents given, denied or withdrawn by her;\n"
     "(b) Notices preceding or accompanying requests for consent; and\n"
     "(c) Sharing of her personal data with a transferee Data Fiduciary.\n\n"
     "4. The Consent Manager —\n"
     "(a) shall give the Data Principal using such platform access to such record;\n"
     "(b) shall, on the request of the Data Principal and in accordance with its terms of service, make "
     "available to her the information contained in such record, in machine-readable form; and\n"
     "(c) shall maintain such record for at least seven years, or for such longer period as the Data Principal "
     "and Consent Manager may agree upon or as may be required by law.\n\n"
     "5. The Consent Manager shall develop and maintain a website or app, or both, as the primary means "
     "through which a Data Principal may access the services provided by the Consent Manager.\n\n"
     "6. The Consent Manager shall not sub-contract or assign the performance of any of its obligations under "
     "the Act and these rules.\n\n"
     "7. The Consent Manager shall take reasonable security safeguards to prevent personal data breach.\n\n"
     "8. The Consent Manager shall act in a fiduciary capacity in relation to the Data Principal.\n\n"
     "9. The Consent Manager shall avoid conflict of interest with Data Fiduciaries, including in respect of "
     "their promoters and key managerial personnel.\n\n"
     "10. The Consent Manager shall have in place measures to ensure that no conflict of interest arises on "
     "account of its directors, key managerial personnel and senior management holding a directorship, "
     "financial interest, employment or beneficial ownership in Data Fiduciaries, or having a material "
     "pecuniary relationship with them.\n\n"
     "11. The Consent Manager shall publish in an easily accessible manner, on its website or app, or both, as "
     "the case may be, information regarding: —\n"
     "(a) the promoters, directors, key managerial personnel and senior management of the company registered "
     "as Consent Manager;\n"
     "(b) every person who holds shares in excess of two per cent. of the shareholding of the company "
     "registered as Consent Manager;\n"
     "(c) every body corporate in whose shareholding any promoter, director, key managerial personnel or "
     "senior management of the Consent Manager holds shares in excess of two per cent. as on the first day of "
     "the preceding calendar month; and\n"
     "(d) such other information as the Board may direct the Consent Manager to disclose in the interests of "
     "transparency.\n\n"
     "12. The Consent Manager shall have in place effective audit mechanisms to review, monitor, evaluate and "
     "report the outcome of such audit to the Board, periodically and on such other occasions as the Board may "
     "direct, in respect of —\n"
     "(a) technical and organisational controls, systems, procedures and safeguards;\n"
     "(b) continued fulfilment of the conditions of registration; and\n"
     "(c) adherence to its obligations under the Act and these rules.\n\n"
     "13. The control of the company registered as the Consent Manager shall not be transferred by way of "
     "sale, merger or otherwise, except with the previous approval of the Board and subject to fulfilment of "
     "such conditions as the Board may specify in this behalf."),

    ("DPDPR-SCH2", "Second Schedule", "Exemptions",
     "Sets, in full, the processing standards that State bodies (for benefit/service delivery) and research/archival/statistical processing must follow — lawfulness, purpose limitation, data minimisation, accuracy, retention limits, security safeguards, and accountability.",
     EFF_GROUP_C,
     "**Second Schedule** *(see rules 5(1) and 16)*\n\n"
     "**Standards for processing of personal data by State and its instrumentalities under clause (b) of "
     "section 7 and for processing of personal data necessary for the purposes specified in clause (b) of "
     "sub-section (2) of section 17**\n\n"
     "Implementation of appropriate technical and organisational measures to ensure effective observance of "
     "the following, in accordance with applicable law, for the processing of personal data, namely: —\n\n"
     "(a) Processing is carried out in a lawful manner;\n\n"
     "(b) Processing is done for the uses specified in clause (b) of section 7 of the Act or for the purposes "
     "specified in clause (b) of sub-section (2) of section 17 of the Act, as the case may be;\n\n"
     "(c) Processing is limited to such personal data as is necessary for such uses or achieving such "
     "purposes, as the case may be;\n\n"
     "(d) Processing is done while making reasonable efforts to ensure the completeness, accuracy and "
     "consistency of personal data;\n\n"
     "(e) Personal data is retained till required for such uses or achieving such purposes, as the case may "
     "be, or for compliance with any law for the time being in force;\n\n"
     "(f) Reasonable security safeguards to prevent personal data breach to protect personal data in the "
     "possession or under control of the Data Fiduciary, including in respect of any processing undertaken by "
     "it or on its behalf by a Data Processor;\n\n"
     "(g) Where processing is to be done under clause (b) of section 7 of the Act, the same is undertaken "
     "while giving the Data Principal an intimation in respect of the same and —\n"
     "(i) giving the business contact information of a person who is able to answer on behalf of the Data "
     "Fiduciary the questions of the Data Principal about the processing of her personal data;\n"
     "(ii) specifying the particular communication link for accessing the website or app, or both, of such "
     "Data Fiduciary, and a description of other means, if any, using which such Data Principal may exercise "
     "her rights under the Act; and\n"
     "(iii) is carried on in a manner consistent with such other standards as may be applicable to the "
     "processing of such personal data under policy issued by the Central Government or any law for the time "
     "being in force; and\n\n"
     "(h) Accountability of the person who alone or in conjunction with other persons determines the purpose "
     "and means of processing of personal data, for effective observance of these standards."),

    ("DPDPR-SCH3", "Third Schedule", "Retention & Erasure",
     "Lists three classes of large Data Fiduciary (e-commerce with 2cr+ users, online gaming with 50L+ users, social media with 2cr+ users) that must erase personal data three years after the Data Principal's last contact for most purposes — subject to Rule 8(1).",
     EFF_GROUP_C,
     "**Third Schedule** *(see rule 8(1))*\n\n"
     "| Class of Data Fiduciaries | Purposes | Time period |\n"
     "|---|---|---|\n"
     "| Data Fiduciary who is an e-commerce entity having not less than two crore registered users in India. "
     "| For all purposes, except: (a) enabling the Data Principal to access her user account; and (b) enabling "
     "the Data Principal to access any virtual token issued by or on behalf of the Data Fiduciary, stored on "
     "its digital facility/platform, usable to get money, goods or services. | Three years from the date the "
     "Data Principal last approached the Data Fiduciary for the specified purpose or exercise of rights, or "
     "commencement of the Rules, whichever is latest. |\n"
     "| Data Fiduciary who is an online gaming intermediary having not less than fifty lakh registered users "
     "in India. | Same exceptions as above. | Same three-year rule as above. |\n"
     "| Data Fiduciary who is a social media intermediary having not less than two crore registered users in "
     "India. | Same exceptions as above. | Same three-year rule as above. |\n\n"
     "**Note:** In this Schedule —\n"
     "(a) \"e-commerce entity\" means any person who owns, operates or manages a digital facility or platform "
     "for e-commerce as defined in the Consumer Protection Act, 2019 (35 of 2019), but does not include a "
     "seller offering her goods or services for sale on a marketplace e-commerce entity as defined in the said "
     "Act;\n"
     "(b) \"online gaming intermediary\" means any intermediary who enables the users of its computer resource "
     "to access one or more online games;\n"
     "(c) \"social media intermediary\" means an intermediary as defined in clause (w) of sub-rule (1) of rule "
     "2 of the Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021; and\n"
     "(d) \"user\", in relation to an e-commerce entity, means any person who accesses or avails any computer "
     "resource of an e-commerce entity; and in relation to an online gaming intermediary or a social media "
     "intermediary, means any person who accesses or avails of any computer resource of an intermediary for "
     "the purpose of hosting, publishing, sharing, transacting, viewing, displaying, downloading or uploading "
     "information."),

    ("DPDPR-SCH4", "Fourth Schedule", "Children & Persons with Disabilities",
     "Sets, in full, Part A's exempted Data Fiduciary classes (clinical/mental-health establishments, healthcare professionals, educational institutions, crèches, child transport providers) and Part B's exempted purposes (legal duties, benefit delivery, email accounts, safety location-tracking, harm-prevention, and age-verification itself).",
     EFF_GROUP_C,
     "**Fourth Schedule** *(see rule 12)*\n\n"
     "**PART A — Classes of Data Fiduciaries in respect of whom provisions of sub-sections (1) and (3) of "
     "section 9 shall not apply**\n\n"
     "| Class of Data Fiduciaries | Conditions |\n"
     "|---|---|\n"
     "| A Data Fiduciary who is a clinical establishment, mental health establishment or healthcare "
     "professional. | Processing is restricted to provision of health services to the child by such "
     "establishment or professional, to the extent necessary for the protection of her health. |\n"
     "| A Data Fiduciary who is an allied healthcare professional. | Processing is restricted to supporting "
     "implementation of any healthcare treatment and referral plan recommended by such professional for the "
     "child, to the extent necessary for the protection of her health. |\n"
     "| A Data Fiduciary who is an educational institution. | Processing is restricted to tracking and "
     "behavioural monitoring — (a) for the educational activities of such institution; or (b) in the "
     "interests of safety of children enrolled with such institution. |\n"
     "| A Data Fiduciary who is an individual in whose care infants and children in a crèche or child day "
     "care centre are entrusted. | Processing is restricted to tracking and behavioural monitoring in the "
     "interests of safety of children entrusted in the care of such institution, crèche or centre. |\n"
     "| A Data Fiduciary who is engaged by an educational institution, crèche or child care centre for "
     "transport of children enrolled with such institution, crèche or centre. | Processing is restricted to "
     "tracking the location of such children, in the interests of their safety, during the course of their "
     "travel to and from such institution, crèche or centre. |\n\n"
     "**PART B — Purposes for which provisions of sub-sections (1) and (3) of section 9 shall not apply**\n\n"
     "| Purpose | Conditions |\n"
     "|---|---|\n"
     "| For the exercise of any power, performance of any function or discharge of any duties in the "
     "interests of a child, under any law for the time being in force in India. | Processing is restricted to "
     "the extent necessary for such exercise, performance or discharge. |\n"
     "| For providing or issuing of any subsidy, benefit, service, certificate, licence or permit, by "
     "whatever name called, under law or policy or using public funds, in the interests of a child, under "
     "clause (b) of section 7 of the Act. | Processing is restricted to the extent necessary for such "
     "provision or issuance. |\n"
     "| For the creation of a user account for communicating by email. | Processing is restricted to the "
     "extent necessary for creating such user account, the use of which is limited to communication by "
     "email. |\n"
     "| For the determination of real-time location of a child. | Processing is restricted to the tracking "
     "of real-time location of such child, in the interest of her safety and protection or security. |\n"
     "| For ensuring that any information, service or advertisement likely to cause any detrimental effect "
     "on the well-being of a child is not accessible to her. | Processing is restricted to the extent "
     "necessary to ensure that such information, service or advertisement is not accessible to the child. |\n"
     "| For confirmation by the Data Fiduciary that the Data Principal is not a child and observance of due "
     "diligence under rule 10. | Processing is restricted to the extent necessary for such confirmation or "
     "observance. |"),

    ("DPDPR-SCH5", "Fifth Schedule", "Data Protection Board",
     "Sets Board Chairperson/Member compensation and service terms in full — salary, provident fund, pension/gratuity, travel, medical assistance, leave, leave travel concession, and other conditions.",
     EFF_GROUP_A,
     "**Fifth Schedule** *(see rule 18)*\n\n"
     "**Terms and conditions of service of Chairperson and other Members**\n\n"
     "1. **Salary.** (1) The Chairperson shall be entitled to receive a consolidated salary of rupees four "
     "lakh fifty thousand per month, without the facility of house and car. (2) Every Member other than the "
     "Chairperson shall be entitled to receive a consolidated salary of rupees four lakh per month, without "
     "the facility of house and car.\n\n"
     "2. **Provident Fund.** The Chairperson and every other Member shall be eligible to contribute to the "
     "Provident Fund of the Board, and the manner and terms and conditions applicable in this regard shall, "
     "mutatis mutandis, be the same as those applicable to other officers and employees of the Board for their "
     "Provident Fund.\n\n"
     "3. **Pension and gratuity.** The Chairperson and every other Member shall not be entitled to payment of "
     "pension or gratuity for service rendered in the Board.\n\n"
     "4. **Travelling allowance.** (1) The Chairperson and every other Member, while on transfer to join the "
     "Board, or on the expiry of her term with the Board for proceeding to her home town with family "
     "(including in respect of journey undertaken by her and her family), or on tour within India, shall be "
     "entitled to journey allowance, daily allowance and reimbursement of expense on transportation of "
     "personal effects at such scales and rates as are applicable to an officer of the Central Government in "
     "the following level of the pay matrix, namely: (a) level 17, in the case of the Chairperson; and "
     "(b) level 15, in the case of every other Member. (2) The Chairperson and every other Member may "
     "undertake tour outside India only in accordance with guidelines or instructions issued by the Central "
     "Government, and in respect of such tour, she shall be entitled to draw the same allowances as an "
     "officer of the Central Government, in the following level of the pay matrix, is entitled to draw, "
     "namely: (a) level 17, in the case of the Chairperson; and (b) level 15, in the case of every other "
     "Member.\n\n"
     "5. **Medical assistance.** (1) The Chairperson and every other Member shall be entitled to such medical "
     "assistance as may be admissible to them under any group health insurance scheme of the Board for "
     "officers and employees of the Board and their eligible dependants. (2) If the Chairperson or other "
     "Member has retired from Government service, or from the service of a public sector entity or a body "
     "corporate established by a Central Act, Provincial Act or State Act, and there are a separate set of "
     "rules for the grant of medical assistance for such service, she may, in lieu of medical assistance under "
     "sub-paragraph (1), opt to be governed by such rules.\n\n"
     "6. **Leave.** (1) The authority competent to sanction leave shall be the Central Government in respect "
     "of the Chairperson, and the Chairperson in respect of any other Member. (2) The Chairperson and every "
     "other Member may avail of such kinds of leave as are admissible to a Government servant under sub-clause "
     "(i) of clause (a) and clause (b) of sub-rule (1) of rule 26, rules 27, 29, 30 and 40 to 43-C of the "
     "Central Civil Services (Leave) Rules, 1972 (\"Leave Rules\"). (3) Leave shall be subject to the "
     "conditions applicable to a Government servant under rules 7 to 11 and 22 to 25 of the Leave Rules, and "
     "the Central Government may, if satisfied that the operation of any of the said rules causes undue "
     "hardship in a particular case, by order relax the requirements of that rule to such extent and subject "
     "to such exceptions and conditions as it may consider necessary for dealing with the case in a just and "
     "equitable manner. (4) The Chairperson and every other Member shall be entitled to casual leave to such "
     "extent as is admissible to a Government servant under instructions issued by the Central Government. "
     "(5) The Chairperson and every other Member shall be entitled to encashment of earned leave standing to "
     "her credit, subject to such conditions and in like manner as are applicable to a Government servant "
     "under rule 38-A, sub-rules (1) and (2) and sub-clauses (i) and (ii) of clause (a) of sub-rule (6) of "
     "rule 39, rule 39-A and rule 39-C of the Leave Rules, subject to the maximum extent of encashment under "
     "any of the said rules, other than rule 38-A, being fifty per cent. of the earned leave standing to her "
     "credit.\n\n"
     "7. **Leave travel concession.** (1) Leave travel concession shall be admissible to the Chairperson and "
     "every other Member in accordance with the provisions applicable to persons appointed to civil services "
     "and posts in connection with the affairs of the Union of India under rule 3, clauses (a) and (d) of "
     "rule 4, rules 5 to 15 and rule 17 of the Central Civil Services (Leave Travel Concession) Rules, 1988, "
     "and the entitlement for such concession shall be the same as is applicable to officers of the Central "
     "Government in level 17 of the pay matrix in the case of the Chairperson, and to officers of the Central "
     "Government in level 15 of the pay matrix in the case of a Member. (2) The Chairperson and every other "
     "Member shall be eligible to avail of either leave travel concession to home town or leave travel "
     "concession to any place in India in any period of two years from the date of assumption of their office "
     "as a Member.\n\n"
     "8. **Other terms and conditions of service.** (1) The Chairperson and every other Member shall ensure "
     "absence of conflict of interest in the performance of the functions of her office and shall not have any "
     "such financial or other interests as are likely to prejudicially affect the performance of the functions "
     "of such office. (2) The provisions contained in Part IV to Part IX of the Central Civil Services "
     "(Classification, Control and Appeal) Rules, 1965, as applicable to an officer of the Central Government "
     "who is a member of a Central Civil Services, Group 'A', shall apply, mutatis mutandis, to the "
     "Chairperson and every other Member. (3) The Chairperson and every other Member shall not be entitled to "
     "any sitting fee for attending meetings of the Board. (4) The Chairperson and every other Member shall "
     "not be entitled to any sumptuary allowance. (5) Any matter relating to the conditions of service of the "
     "Chairperson or any other Member, in respect of which no express provision has been made in these rules, "
     "shall be referred to the Central Government for its decision, and the decision of the Central "
     "Government on the same shall be final.\n\n"
     "9. In this Schedule, \"pay matrix\" shall mean the pay matrix specified in Annexure I to the Central "
     "Government's Resolution published in the Official Gazette vide Notification no. 1-2/2016-IC, dated the "
     "25th July, 2016."),

    ("DPDPR-SCH6", "Sixth Schedule", "Data Protection Board",
     "Sets full terms for the Board's officers and employees — deputation appointments, gratuity, travel, medical assistance, leave, leave travel concession, and other service conditions.",
     EFF_GROUP_A,
     "**Sixth Schedule** *(see rule 21(2))*\n\n"
     "**Terms and conditions of appointment and service of officers and employees of Board**\n\n"
     "1. **Classes of officials.** (1) The Board may, in accordance with the Fundamental Rules and applicable "
     "guidelines issued by the Ministry of Personnel, Public Grievances and Pensions, Department of Personnel "
     "and Training, appoint officers and employees on deputation from the Central Government, a State "
     "Government, an autonomous body under the overall control of the Central Government or a State "
     "Government, a statutory body, or a public sector enterprise, for a period not exceeding five years. "
     "(2) The Board may also receive or take on deputation any officer or other employee from the National "
     "Institute for Smart Government, for a period not exceeding five years, with salary and allowances "
     "guided by market standards and on such other terms and conditions as the Board may decide.\n\n"
     "2. **Gratuity.** The officers and employees shall be entitled to payment of such gratuity as may be "
     "admissible under the Payment of Gratuity Act, 1972 (39 of 1972).\n\n"
     "3. **Travelling allowance.** The travelling allowance payable to the officers and employees shall, "
     "mutatis mutandis, be the same as those applicable to the officers and employees of the Central "
     "Government.\n\n"
     "4. **Medical assistance.** The officers and employees shall be entitled to such medical assistance as "
     "may be admissible to them and their eligible dependants under any group health insurance scheme of the "
     "Board, made with the previous approval of the Central Government.\n\n"
     "5. **Leave.** (1) The officers and employees may avail of such kinds of leaves as are admissible to a "
     "Government servant under the Central Civil Services (Leave) Rules, 1972, subject to the conditions "
     "applicable under the said rules, and shall be eligible for encashment of earned leave as provided "
     "therein. (2) The officers and employees shall be entitled to casual leave to such extent as is "
     "admissible to a Government servant under instructions issued by the Central Government.\n\n"
     "6. **Leave travel concession.** Leave travel concession shall be admissible to the officers and "
     "employees appointed under clause (1) of paragraph 1, in accordance with the provisions applicable to "
     "persons appointed to civil services and posts in connection with the affairs of the Union of India under "
     "the Central Civil Services (Leave Travel Concession) Rules, 1988.\n\n"
     "7. **Other terms and conditions of service.** (1) The provisions of the Civil Service (Conduct) Rules, "
     "1964 shall apply to the officers and employees in like manner as applicable to a person appointed to a "
     "civil service or post in connection with the affairs of the Union of India under the said rules. "
     "(2) The provisions contained in Part IV to Part IX of the Central Civil Services (Classification, "
     "Control and Appeal) Rules, 1965 shall apply, mutatis mutandis, to the officers and employees appointed "
     "under clause (1) of paragraph 1, in like manner as applicable to a Government servant under the said "
     "rules. (3) Any matter relating to the terms and conditions of service of the officers and employees "
     "appointed under clause (1) of paragraph 1, in respect of which no express provision has been made in "
     "these rules, shall be referred to the Central Government for its decision, and the decision of the "
     "Central Government on the same shall be final."),

    ("DPDPR-SCH7", "Seventh Schedule", "Other",
     "Lists three purposes for which the Central Government (through a designated authorised person) can call for Data Fiduciary/intermediary information: sovereignty/security use, general lawful-function use, and assessing whether an entity qualifies as a Significant Data Fiduciary. Also the reference point for Rule 8(3)'s one-year log retention purposes.",
     EFF_GROUP_C,
     "**Seventh Schedule** *(see rules 23(1) and 8(3))*\n\n"
     "| Purpose | Authorised person |\n"
     "|---|---|\n"
     "| Use, by the State or any of its instrumentalities, of personal data of a Data Principal in the "
     "interest of sovereignty and integrity of India or security of the State. | Such officer of the State or "
     "of any of its instrumentalities notified under clause (a) of sub-section (2) of section 17 of the Act, "
     "as the Central Government or the head of such instrumentality, as the case may be, may designate in "
     "this behalf. |\n"
     "| Use, by the State or any of its instrumentalities, of personal data of a Data Principal for: (i) "
     "performance of any function under any law for the time being in force in India; or (ii) disclosure of "
     "any information for fulfilling any obligation under any law for the time being in force in India. | "
     "Person authorised under applicable law. |\n"
     "| Carrying out assessment for notifying any Data Fiduciary or class of Data Fiduciaries as Significant "
     "Data Fiduciary. | Such officer of the Central Government, in the Ministry of Electronics and "
     "Information Technology, as the Secretary in charge of the said Ministry may designate in this behalf. |"),
]

CHANGE_TYPE = "New Provision"
DETECTED_BY = "manual-seed:gazette-import"
CONFIDENCE = 0.97


def make_anchor(provision_id: str) -> str:
    """Word bookmark names: letters/digits/underscores only, must start with a letter."""
    anchor = re.sub(r"[^A-Za-z0-9_]", "_", provision_id)
    if not anchor[0].isalpha():
        anchor = "P_" + anchor
    return anchor[:40]


def build_provision_row(pid, ref, topic, summary, eff_group, full_text, idx):
    eff_date, eff_note = eff_group
    change_id = f"CHG-{idx:04d}"
    instrument_type = "Schedule" if ref.startswith(("First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh")) else "Rule"
    return {
        "provision_id": pid,
        "instrument_type": instrument_type,
        "reference": ref,
        "topic_category": topic,
        "current_summary": summary,
        "full_text": full_text,
        "full_text_path": DOCX_PATH,
        "full_text_anchor": make_anchor(pid),
        "sort_order": idx,
        "status": "Active",
        "effective_date": eff_date,
        "last_updated_date": FETCHED_DATE,
        "source_document": SOURCE_DOC,
        "source_url": SOURCE_URL,
        "confidence_score": CONFIDENCE,
        "review_status": "Pending Review",
        "reviewed_by": None,
        "review_date": None,
        "latest_change_id": change_id,
        "notes": eff_note if eff_date > FETCHED_DATE else "Currently in force.",
    }, change_id, eff_note


def build_change_row(change_id, pid, summary, full_text, eff_note):
    return {
        "change_id": change_id,
        "detected_timestamp": f"{FETCHED_DATE} 00:00",
        "provision_id": pid,
        "change_type": CHANGE_TYPE,
        "old_value_summary": None,
        "new_value_summary": summary,
        "old_full_text": None,
        "new_full_text": full_text,
        "source_document": SOURCE_DOC,
        "source_url": SOURCE_URL,
        "detected_by": DETECTED_BY,
        "confidence_score": CONFIDENCE,
        "review_status": "Pending Review",
        "reviewed_by": None,
        "review_date": None,
        "applied_to_master": "Y",
        "notes": f"Initial baseline load from Gazette text. {eff_note}",
    }


def main(db_path=None):
    """db_path: optional override, for tests — seeds a scratch database
    instead of the real db/dpdpa.db. Defaults to the real one."""
    if db_path is None:
        db_path = PROJECT_ROOT / "db" / "dpdpa.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    init_schema(conn)

    verbatim_full_text = load_verbatim_full_text()

    prov_cols = None
    change_cols = None
    n = 0

    for i, (pid, ref, topic, summary, eff_group, _tuple_full_text) in enumerate(PROVISIONS, start=2):
        full_text = verbatim_full_text[pid]
        prov_row, change_id, eff_note = build_provision_row(pid, ref, topic, summary, eff_group, full_text, i)
        change_row = build_change_row(change_id, pid, summary, full_text, eff_note)

        if prov_cols is None:
            prov_cols = list(prov_row.keys())
        if change_cols is None:
            change_cols = list(change_row.keys())

        conn.execute(
            f"INSERT OR REPLACE INTO provisions ({','.join(prov_cols)}) "
            f"VALUES ({','.join('?' for _ in prov_cols)})",
            [prov_row[c] for c in prov_cols],
        )
        conn.execute(
            f"INSERT OR REPLACE INTO change_log ({','.join(change_cols)}) "
            f"VALUES ({','.join('?' for _ in change_cols)})",
            [change_row[c] for c in change_cols],
        )
        n += 1

    source_row = {
        "document_id": "SRC-0001",
        "source": "eGazette",
        "title": "Digital Personal Data Protection Rules, 2025 — Gazette Notification G.S.R. 846(E)",
        "url": SOURCE_URL,
        "published_date": "2025-11-13",
        "fetched_date": FETCHED_DATE,
        "content_hash": "manual-seed-not-hashed",
        "processing_status": "Processed",
        "linked_change_ids": ",".join(f"CHG-{i:04d}" for i in range(2, 2 + n)),
    }
    conn.execute(
        f"INSERT OR REPLACE INTO source_log ({','.join(source_row)}) "
        f"VALUES ({','.join('?' for _ in source_row)})",
        list(source_row.values()),
    )

    conn.commit()
    conn.close()
    print(f"Loaded {n} Rules provisions (verbatim, no abridging) and {n} change_log rows.")


if __name__ == "__main__":
    main()
