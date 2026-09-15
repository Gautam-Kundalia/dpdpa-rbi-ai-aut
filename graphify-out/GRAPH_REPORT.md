# Graph Report - dpdpa-rbi-ai-aut  (2026-09-15)

## Corpus Check
- 97 files · ~78,125 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 1, .db 1)

## Summary
- 192 nodes · 309 edges · 17 communities (11 shown, 6 thin omitted)
- Extraction: 80% EXTRACTED · 19% INFERRED · 1% AMBIGUOUS · INFERRED: 59 edges (avg confidence: 0.88)
- Token cost: 352,712 input · 0 output

## Community Hubs (Navigation)
- Apply & Store Pipeline
- Consent & Child Protection Rules
- Data Principal Rights & Board Setup
- Board Enforcement & Appeals
- Consent Manager & Rules Schedules
- Excel Tracker Export
- Word Document Export
- Python Dependencies
- LLM Change Classification
- Database Seeding
- Email Notification
- Section 27(1)(d) Board Power
- Section 31 Dispute Resolution
- Section 34 Penalty Fund
- Section 35 Good Faith Protection
- Section 36 Information Powers
- Section 38 Law Consistency

## God Nodes (most connected - your core abstractions)
1. `get_connection()` - 18 edges
2. `DPDP Rules, 2025 — consolidated text` - 16 edges
3. `Rule 1 — Short title and commencement` - 15 edges
4. `DPDP Rules Tracker — regulatory change tracking workbook` - 15 edges
5. `init_schema()` - 14 edges
6. `fetch_all()` - 11 edges
7. `classify()` - 8 edges
8. `main()` - 8 edges
9. `DPDPA Section 18 — Establishment of Board` - 8 edges
10. `apply()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `DPDP Rules Tracker — regulatory change tracking workbook` --conceptually_related_to--> `Sixth Schedule — Terms of service of Board officers and employees`  [AMBIGUOUS]
  graphify-out/converted/DPDP_Rules_Tracker_106b1f53.md → docs/full_text/DPDPR-SCH6.md
- `DPDP Rules Tracker — regulatory change tracking workbook` --conceptually_related_to--> `Rule 13 — Additional obligations of Significant Data Fiduciary`  [AMBIGUOUS]
  graphify-out/converted/DPDP_Rules_Tracker_106b1f53.md → docs/full_text/DPDPR-SDF-R13.md
- `DPDPA Section 1 — Short title and commencement` --conceptually_related_to--> `Obsolete per-provision full_text markdown design`  [INFERRED]
  docs/full_text/DPDPA-S1.md → README.md
- `DPDPA Section 27(1)(a)-(c),(e),(2),(3) — Powers and functions of Board` --conceptually_related_to--> `Obsolete per-provision full_text markdown design`  [INFERRED]
  docs/full_text/DPDPA-S27.1a_c_e_2_3.md → README.md
- `Rule 7 — Intimation of personal data breach` --conceptually_related_to--> `DPDP Rules, 2025 — consolidated text`  [INFERRED]
  docs/full_text/DPDPR-R7.md → graphify-out/converted/DPDP_Rules_2025_86745c80.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Data Protection Board establishment, composition and governance provisions** — docs_full_text_dpdpa_s18, docs_full_text_dpdpa_s19, docs_full_text_dpdpa_s20, docs_full_text_dpdpa_s21, docs_full_text_dpdpa_s22, docs_full_text_dpdpa_s23, docs_full_text_dpdpa_s24, docs_full_text_dpdpa_s25, docs_full_text_dpdpa_s26, docs_full_text_dpdpa_s27_1a_c_e_2_3 [EXTRACTED 0.90]
- **Data Principal rights and duties provisions** — docs_full_text_dpdpa_s11, docs_full_text_dpdpa_s12, docs_full_text_dpdpa_s13, docs_full_text_dpdpa_s14, docs_full_text_dpdpa_s15 [EXTRACTED 0.90]
- **README, CI workflow, and obsolete full_text design describing the automation pipeline** — readme, github_workflows_daily_check, docs_full_text_obsolete_design [EXTRACTED 0.85]
- **Board inquiry, voluntary undertaking, and penalty enforcement process** — docs_full_text_dpdpa_s28_section_28, docs_full_text_dpdpa_s32_section_32, docs_full_text_dpdpa_s33_section_33 [INFERRED 0.85]
- **Appeal to Appellate Tribunal and decree-based execution, insulated from civil court jurisdiction** — docs_full_text_dpdpa_s29_section_29, docs_full_text_dpdpa_s30_section_30, docs_full_text_dpdpa_s39_section_39 [INFERRED 0.80]
- **Central Government's rule-making, Schedule-amendment, and difficulty-removal powers, subject to parliamentary laying** — docs_full_text_dpdpa_s40_section_40, docs_full_text_dpdpa_s41_section_41, docs_full_text_dpdpa_s42_section_42, docs_full_text_dpdpa_s43_section_43 [INFERRED 0.85]
- **Data Protection Board formation, remuneration, procedure and staffing** — docs_full_text_dpdpr_r17_board_appointment, docs_full_text_dpdpr_r18_board_salary, docs_full_text_dpdpr_r19_board_meeting_procedure, docs_full_text_dpdpr_r20_board_digital_office, docs_full_text_dpdpr_r21_board_staff [INFERRED 0.90]
- **Verifiable consent mechanism for children and persons with disabilities** — docs_full_text_dpdpa_s9_children_processing, docs_full_text_dpdpr_r10_child_verifiable_consent, docs_full_text_dpdpr_r11_disability_verifiable_consent, docs_full_text_dpdpr_r2_definitions [INFERRED 0.90]
- **Consent and notice lifecycle: notice, consent grant/withdrawal, Consent Manager** — docs_full_text_dpdpa_s6_1_8_10_consent_notice, docs_full_text_dpdpa_s6_9_consent_manager_registration, docs_full_text_dpdpr_r3_notice_requirements [INFERRED 0.85]
- **Consent Manager registration and obligations flow (Act s.6(9), Rule 4, First Schedule)** — graphify_out_converted_dpdp_act_2023_7c48f170_document, docs_full_text_dpdpr_r4_rule4_consent_manager, docs_full_text_dpdpr_sch1_first_schedule_consent_manager [INFERRED 0.90]
- **Breach notification, security safeguards, and Board enforcement flow** — graphify_out_converted_dpdp_act_2023_7c48f170_document, docs_full_text_dpdpr_r6_rule6_security_safeguards, docs_full_text_dpdpr_r7_rule7_breach_notification [INFERRED 0.80]
- **Retention and erasure scheme (purpose-lapse erasure, log retention, Third/Seventh Schedules)** — docs_full_text_dpdpr_r8_1_2_rule8_1_2_retention, docs_full_text_dpdpr_r8_3_rule8_3_log_retention, docs_full_text_dpdpr_sch3_third_schedule_erasure_classes, docs_full_text_dpdpr_sch7_seventh_schedule_purposes_authorised_persons [INFERRED 0.85]

## Communities (17 total, 6 thin omitted)

### Community 0 - "Apply & Store Pipeline"
Cohesion: 0.11
Nodes (33): Connection, Path, apply(), _docx_path_for(), _make_anchor(), Apply a classified change: insert it into change_log (auto-approved — no human…, Insert `change` into change_log, then apply it to `provisions`: - New Provision…, get_connection() (+25 more)

### Community 1 - "Consent & Child Protection Rules"
Cohesion: 0.10
Nodes (30): Consent Manager (concept), Data Protection Board (concept), Verifiable Consent (concept), S6(1)-(8),(10) — Consent, S6(9) — Registration of Consent Manager, S7 — Certain legitimate uses, S8 — General obligations of Data Fiduciary, S9 — Processing of personal data of children (+22 more)

### Community 2 - "Data Principal Rights & Board Setup"
Cohesion: 0.11
Nodes (23): DPDPA Section 1 — Short title and commencement, DPDPA Section 10 — Additional obligations of Significant Data Fiduciary, DPDPA Section 11 — Right to access information about personal data, DPDPA Section 12 — Right to correction and erasure of personal data, DPDPA Section 13 — Right of grievance redressal, DPDPA Section 14 — Right to nominate, DPDPA Section 15 — Duties of Data Principal, DPDPA Section 16 — Processing of personal data outside India (+15 more)

### Community 3 - "Board Enforcement & Appeals"
Cohesion: 0.11
Nodes (21): Section 28 — Procedure to be followed by Board, Section 29 — Appeal to Appellate Tribunal, Telecom Regulatory Authority of India Act, 1997, Section 30 — Orders passed by Appellate Tribunal to be executable as decree, Section 32 — Voluntary undertaking, Section 33 — Penalties, Information Technology Act, 2000, Section 37 — Power of Central Government to issue directions (+13 more)

### Community 4 - "Consent Manager & Rules Schedules"
Cohesion: 0.25
Nodes (18): Rule 4 — Registration and obligations of Consent Manager, Rule 5 — Processing for State subsidy/benefit/service delivery, Rule 6 — Reasonable security safeguards, Rule 7 — Intimation of personal data breach, Rule 8(1)-(2) — Time period for specified purpose to be deemed no longer served, Rule 8(3) — Retention of processing logs, Rule 9 — Contact information of person to answer processing questions, First Schedule — Consent Manager registration & obligations (+10 more)

### Community 5 - "Excel Tracker Export"
Cohesion: 0.27
Nodes (10): add_in_force_column(), add_list_validation(), build_readme(), main(), Generate the human-facing Excel tracker from db/dpdpa.db. SQLite is the source…, Computed column: Yes/No based on comparing today's date to Effective_Date.…, set_widths(), style_header() (+2 more)

### Community 6 - "Word Document Export"
Cohesion: 0.28
Nodes (12): add_bookmark(), add_inline_runs(), add_internal_hyperlink(), add_markdown_table(), build_document(), fetch_latest_amendment(), fetch_provisions(), is_table_block() (+4 more)

### Community 7 - "Python Dependencies"
Cohesion: 0.25
Nodes (8): beautifulsoup4, openpyxl, dpdpa-rbi-ai-aut pipeline project, pypdf, python-docx, python-dotenv, pyyaml, requests

### Community 8 - "LLM Change Classification"
Cohesion: 0.39
Nodes (7): _build_user_prompt(), _call_openrouter(), classify(), _current_provisions(), Classify a changed source's content against current `provisions` using…, Classify one changed source. Returns a validated list of change dicts (possibly…, _validate()

### Community 9 - "Database Seeding"
Cohesion: 0.43
Nodes (6): build_change_row(), build_provision_row(), main(), make_anchor(), Seed db/dpdpa.db with the full Digital Personal Data Protection Act, 2023 — all…, Word bookmark names: letters/digits/underscores only, must start with a letter.

### Community 10 - "Email Notification"
Cohesion: 0.53
Nodes (5): EmailMessage, _attach_docs(), _build_body(), Send one summary email per pipeline run via Gmail SMTP (smtplib + ssl, app…, send_summary()

## Ambiguous Edges - Review These
- `DPDPA Section 1 — Short title and commencement` → `DPDPA Section 2 — Definitions`  [AMBIGUOUS]
  docs/full_text/DPDPA-S2.md · relation: conceptually_related_to
- `Sixth Schedule — Terms of service of Board officers and employees` → `DPDP Rules Tracker — regulatory change tracking workbook`  [AMBIGUOUS]
  graphify-out/converted/DPDP_Rules_Tracker_106b1f53.md · relation: conceptually_related_to
- `Seventh Schedule — Purposes and authorised persons` → `DPDP Rules Tracker — regulatory change tracking workbook`  [AMBIGUOUS]
  graphify-out/converted/DPDP_Rules_Tracker_106b1f53.md · relation: conceptually_related_to
- `Rule 13 — Additional obligations of Significant Data Fiduciary` → `DPDP Rules Tracker — regulatory change tracking workbook`  [AMBIGUOUS]
  graphify-out/converted/DPDP_Rules_Tracker_106b1f53.md · relation: conceptually_related_to

## Knowledge Gaps
- **38 isolated node(s):** `Daily DPDP regulatory change check workflow`, `DPDPA Section 14 — Right to nominate`, `DPDPA Section 15 — Duties of Data Principal`, `DPDPA Section 16 — Processing of personal data outside India`, `DPDPA Section 20 — Salary, allowances and term of office` (+33 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 62 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `DPDPA Section 1 — Short title and commencement` and `DPDPA Section 2 — Definitions`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Sixth Schedule — Terms of service of Board officers and employees` and `DPDP Rules Tracker — regulatory change tracking workbook`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Seventh Schedule — Purposes and authorised persons` and `DPDP Rules Tracker — regulatory change tracking workbook`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Rule 13 — Additional obligations of Significant Data Fiduciary` and `DPDP Rules Tracker — regulatory change tracking workbook`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `get_connection()` connect `Apply & Store Pipeline` to `Database Seeding`, `Excel Tracker Export`, `Word Document Export`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `init_schema()` connect `Apply & Store Pipeline` to `Database Seeding`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `DPDP Rules, 2025 — consolidated text` (e.g. with `Rule 4 — Registration and obligations of Consent Manager` and `Rule 5 — Processing for State subsidy/benefit/service delivery`) actually correct?**
  _`DPDP Rules, 2025 — consolidated text` has 15 INFERRED edges - model-reasoned connections that need verification._