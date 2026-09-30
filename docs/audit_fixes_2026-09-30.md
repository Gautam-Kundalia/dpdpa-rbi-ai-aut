# Audit fixes, 30 September 2026 — every finding, and what happened to it

**The audit:** `Claude outputs/AUDIT_REPORT_2026-09-30_opus.md`, an independent
review of commit `6022d45` by a separate Claude Opus session. It raised
**4 Critical, 7 High, 14 Medium and 9 Low findings**, plus 7 "Info" notes that
are mostly things the project gets right.

**The work:** branch `audit-fixes-2026-09-30`. **Not pushed, not merged** —
publishing is Gautam's decision.

**This file is the checklist.** Every finding in the audit has a row. Nothing is
silently dropped. If a finding was not fixed, the row says so and why.

For the story of how the work went — including which evidence was watched live
and which was read off a committed diff — see
`docs/audit_fixes_2026-09-30_session_report.md`. For plain-language summaries of
each session, see `CHANGELOG.md`.

## What the status words mean

| Status | Meaning |
|---|---|
| **Fixed** | Changed in code on this branch, with a test that fails without the fix. |
| **Fixed by script Gautam runs** | The code and the one-off script are written and tested on a throwaway copy of the database, but the real `db/dpdpa.db` is only changed when Gautam runs the script. Nothing here has been run against the live database. |
| **Deliberately not done** | A decision, not an oversight. The reason is given. |
| **Not a problem** | Checked, and the finding does not hold — or it describes something that is working as intended. |
| **Not verifiable here** | Could not be checked from this machine or this session. Said plainly rather than assumed. |

---

## Critical

| ID | The problem, in one line | Status | Where the fix lives | Which test proves it |
|---|---|---|---|---|
| **C-1** | The Act's "permanent verbatim guard" rebuilt the text from the PDF and then checked *that*, so it never read the database and could not fail. | Fixed | `scripts/rebuild_act_verbatim_2026-09-23.py` — `run_checks()` now reads `provisions.full_text` | `tests/test_legal_text_verbatim.py` (the Act checks, plus their mutation tests) |
| **C-2** | Neither verbatim guard noticed a single-word swap that reverses a rule's meaning: the 97% word-set fallback asked only whether each word appeared *somewhere*, ignoring order. `shall`→`may` and `six months`→`six years` both passed. | Fixed | `tests/test_legal_text_verbatim.py` — word-set fallback replaced by an ordered comparison (`_ordered_match`, `ORDERED_RATIO_MIN = 0.995`); reviewed differences are exact pairs that expire by themselves | `test_rules_check_fails_on_a_meaning_changing_word_swap`, `test_a_deleted_space_is_caught`, `test_two_words_swapped_round_is_caught`, `test_a_dropped_clause_is_caught`, `test_an_exception_does_not_shelter_the_rest_of_its_provision` |
| **C-3** | The DPDP Rules PDF (the single most important document here) had a fingerprint but no stored baseline text, so its next change would have been stored as the baseline and reported as "no change". | Fixed, plus a script Gautam runs | `src/fetch_sources.py` writes the snapshot when a source is first recorded; `src/classify_change.py` tells a genuine first sighting apart from a data-integrity fault and *raises* on the latter; `scripts/backfill_source_snapshots_2026-09-30.py` repairs the existing gap | `tests/test_pipeline_failures.py` |
| **C-4** | Any text on any watched page could be written into `provisions.full_text` — the audit proved it with a forged notice — and the e-Gazette host was fetched with TLS verification switched off. | Fixed | `src/fetch_sources.py` (`may_amend` authority table, fails closed), enforced in **both** `classify_change.classify()` and `apply_change.apply()`; PIB is alert-only with no AI call; the e-Gazette home page is retired; `certs/egazette-chain.pem` pins the certificate instead of disabling the check | `tests/test_source_authority.py`, `tests/test_egazette_chain.py` |

---

## High

| ID | The problem, in one line | Status | Where the fix lives | Which test proves it |
|---|---|---|---|---|
| **H-1** | No dead-man's switch: every warning travelled down the one channel (email) that can itself fail silently. | Fixed | `.github/workflows/daily-check.yml` — heartbeat ping with `if: always()` | Workflow change; **Gautam must still create the healthchecks.io check and add the `HEARTBEAT_URL` secret**, or the ping goes nowhere |
| **H-2** | A change `apply_change` safely refused was reported once and then lost forever, because the fingerprint had already moved on. | Fixed | `src/run_pipeline.py` — the snapshot *and* the fingerprint are rolled back on failure, so tomorrow retries | `tests/test_pipeline_failures.py` |
| **H-3** | The verbatim guards never ran automatically; there was no test CI at all. | Fixed | `.github/workflows/tests.yml` | The workflow itself; **Gautam should confirm it is green on GitHub after the merge** |
| **H-4** | All 79 "Open full text" links in the committed Excel pointed into a deleted sandbox (`/tmp/claude-0/...`). | Fixed in code; the committed `.xlsx` is only corrected when it is next regenerated | `src/export_excel.py` — `_workbook_relative()` | `test_no_hyperlink_is_an_absolute_path`, `test_hyperlinks_are_relative_to_the_workbook`, `test_the_link_really_points_at_the_document` |
| **H-5** | Two of the corrigendum's six items were recorded as "our own data correction", so two real acts of government were never highlighted or reported. | Fixed by script Gautam runs — **and the wording needs his approval first** | `scripts/fix_corrigendum_schedules_2026-09-30.py` (dry-run by default) | `tests/test_data_fix_scripts.py` — the four-row test, the uniqueness test, the twice-safe test, and the yellow-row/highlight test |
| **H-6** | A data correction applied after a real amendment moved `latest_change_id`, so the amendment's highlighting, caption and Excel cell silently vanished. The README claimed data corrections "never affect rendering". | Fixed | `src/export_word.py` — `fetch_amendments()` / `QUALIFYING_AMENDMENTS_SQL`; `src/export_excel.py` reuses it | `test_a_later_data_correction_does_not_hide_a_government_amendment`, `test_a_data_correction_on_its_own_still_renders_nothing`, `test_a_data_correction_does_not_change_what_is_highlighted` |
| **H-7** | One real paraphrase in the legal text: the Seventh Schedule replaced five words of enacted law ("the following purposes, namely") with a colon. | Fixed by script Gautam runs | `scripts/restore_verbatim_wording_2026-09-30.py` (dry-run by default) | `test_applying_restores_the_wording_as_our_own_correction`, `test_the_restored_text_matches_the_official_pdf_without_any_exception` |

---

## Medium

| ID | The problem, in one line | Status | Where the fix lives | Which test proves it |
|---|---|---|---|---|
| **M-1** | Only the most recent change to a provision was ever shown, so a provision amended twice looked as though it had been amended once. | Fixed | `src/export_word.py` (`fetch_amendments`, `add_amendment_caption`, `render_provision_body`), `src/export_excel.py` (`Last_Regulatory_Change` adds "(+N earlier)") | `test_two_amendments_to_one_provision_are_both_rendered`, `test_the_excel_column_says_how_much_earlier_history_there_is`, `test_an_amendment_whose_text_has_moved_on_is_captioned_but_not_highlighted` |
| **M-2** | A validation failure that can never succeed was retried three times, at three times the cost. | Fixed | `src/classify_change.py` — a deterministic failure is not retried | `tests/test_run_reliability.py` |
| **M-3** | The e-Gazette fetch failed on roughly 30% of days, so error emails became routine and the important one would be missed. | Fixed | `src/fetch_sources.py` (one retry after a pause), `src/db.py` (`error_signature`, `error_streak_days`, `error_streak_last_date`), `src/notify.py` (a repeated error stops shouting on the subject line but stays in the body) | `tests/test_error_noise.py` |
| **M-4** | 100% of the routine daily AI call was noise, and it shipped all 79 provisions. | Fixed | `src/fetch_sources.py` + `src/classify_change.py` — the retired e-Gazette home page was the source of that call; PIB makes no AI call at all | `tests/test_source_authority.py` |
| **M-5** | `source_log` held 7 rows for 4 watched URLs, while the README and the Excel sheet both said it showed "what's being watched right now". | Fixed, plus a script Gautam runs | `src/db.py` (additive `watched` column, default 1), `src/export_excel.py` (sheet shows only `watched = 1`, README sheet wording corrected), `scripts/mark_unwatched_sources_2026-09-30.py` | `test_the_exported_source_log_sheet_really_leaves_the_retired_rows_out`, `test_the_tracker_can_be_rebuilt_on_a_database_that_predates_the_watched_column`, `test_applying_retires_exactly_four_sources_and_deletes_nothing` |
| **M-6** | The discovery scrape never checked the count the results page itself reports, so a half-read page looked like "nothing new". | Fixed | `src/discover_documents.py` — reads `#lbl_Result` and raises on a mismatch | `test_a_month_whose_count_disagrees_is_a_loud_failure`, `test_a_month_whose_count_agrees_is_accepted`, `test_an_unreadable_count_label_warns_but_keeps_going` |
| **M-7** | One malformed Gazette ID threw away the whole day's discovery listing. | Fixed | `src/discover_documents.py` — the good rows are kept, the bad one is named for a human and reaches the run's error list | `test_a_bad_gazette_id_keeps_the_good_rows`, `test_a_discovery_warning_reaches_the_runs_error_list` |
| **M-8** | Floating action versions, no concurrency group, no push retry, on a job with write access. | Fixed | `.github/workflows/daily-check.yml` | The workflow file; verified by reading, not by a test — GitHub Actions cannot be exercised from here |
| **M-9** | A stale OpenRouter API key is still in `.env`. | **Only Gautam can do this** | — | — · **Revoke the key first, then delete its two lines from `.env`.** Deleting the lines without revoking leaves a live key loose. |
| **M-10** | `confidence_score` is recorded but gates nothing. | Deliberately not done | — | The audit measured a **genuine** amendment at 0.65, so a threshold would block real changes. Confidence is recorded and does not gate; now stated in `README.md` and in the Excel README sheet |
| **M-11** | Fifteen Fifth/Sixth Schedule paragraph headings drop the Gazette's separator dash. | Fixed by script Gautam runs | `scripts/restore_verbatim_wording_2026-09-30.py` | `test_all_fifteen_heading_dashes_are_shown_before_and_after`, `test_applying_restores_the_wording_as_our_own_correction` |
| **M-12** | The discovery window was fixed at two months, so an outage longer than a month lost documents permanently. | Fixed | `src/discover_documents.py` — `_months_to_search`, widens after 25 days, capped at 12 months, always reported | `test_an_ordinary_day_searches_two_months`, `test_a_long_outage_widens_the_window_and_says_so`, `test_a_very_long_outage_is_capped_and_the_gap_is_named` |
| **M-13** | `mark_alerted` opened the default database, not the pipeline's. | Fixed | `src/run_pipeline.py` / `src/discover_documents.py` — the connection is passed in | `tests/test_run_reliability.py` |
| **M-14** | The commit step ran `if: always()`, so a run killed mid-flight committed a database that no longer matched the documents. | Fixed | `.github/workflows/daily-check.yml` + `src/run_pipeline.py` — the run must have reached the end | `tests/test_run_reliability.py` |

---

## Low

| ID | The problem, in one line | Status | Where the fix lives | Which test proves it |
|---|---|---|---|---|
| **L-1** | Rules `sort_order` starts at 2; there is no row with `sort_order = 1`. | Deliberately not done | — | Harmless display gap. Out of scope by instruction; recorded as a follow-up |
| **L-2** | `DPDPR-SDF-R13` breaks the ID convention every other row follows. | Deliberately not done | — | Renaming a primary key touches bookmarks, change history and tests. Out of scope by instruction; recorded as a follow-up |
| **L-3** | The Excel `In_Force` column showed `#VALUE!` for a date the reader's Excel locale could not parse. | Fixed | `src/export_excel.py` — `IFERROR(...)` around `DATEVALUE` | `test_the_in_force_formula_cannot_show_an_error_value` |
| **L-4** | The schema allows `'Sub-Rule'`, `'Notification'`, `'Board Order'` and `'Data Protection Board'`, which no code path ever produces — so it promises coverage that does not exist. | Deliberately not done, but written down | — | Out of scope by instruction. Named in `README.md` "Known limitations" so nobody assumes Board orders are watched |
| **L-5** | `notify._attach_docs` raised `KeyError` on an unknown file extension, which the caller turned into "notify failed". | Fixed | `src/notify.py` — defaults to `application/octet-stream` | `test_an_unexpected_attachment_type_does_not_crash_the_email` |
| **L-6** | The Act verbatim test wrote two *tracked* files and repaired them with `git checkout --`; if it failed mid-way it left the working tree dirty. | Fixed | `scripts/rebuild_act_verbatim_2026-09-23.py` gained `--out-dir`; `tests/test_legal_text_verbatim.py` `_run_act_check()` writes into `tmp_path` and copies the database first, so nothing tracked by git is touched and no `git checkout --` remains | `test_act_table_passes_verbatim_checks_c1_to_c5` — and, in practice, `git status` staying clean after a full test run |
| **L-7** | `CLAUDE.md` said PyMuPDF "cannot load locally (blocked DLL)", steering work away from a tool that now works. | Fixed — **and re-checked on this machine before editing** | `CLAUDE.md` | Checked directly: `import pymupdf` and `import fitz` both succeed, PyMuPDF **1.28.2**. `fitz` prints a deprecation warning. The old note was true once; it is not now |
| **L-8** | The generated Word documents did not say when they were made, how current they are, that they are not legal advice, or that the Rules text incorporates G.S.R. 892(E). | Fixed | `src/export_word.py` — `DOCX_SPECS` provenance + `provenance_lines()` | `test_both_documents_carry_provenance_and_a_disclaimer`, `test_the_rules_document_names_the_corrigendum`, `test_the_documents_say_how_current_the_text_is` |
| **L-9** | 19 of 79 provisions have `topic_category = 'Other'`, so the Word contents page reads "Rule 1 — Other". | Deliberately not done | — | Out of scope by instruction (do not touch `topic_category`). Cosmetic; recorded as a follow-up |

---

## Info — the audit's "things that are right"

None of these needed a fix. They are recorded because a later session should not
"helpfully" undo them.

| ID | What it says | Still true? |
|---|---|---|
| **I-1** | The generated documents are faithful to the database — regenerating reproduced the committed files run-for-run. | **Re-confirmed on 30 Sep 2026.** Regenerating from the committed database with this branch's code reproduces `main`'s output exactly in body text and highlighting (4 yellow spans, 3 strike-throughs, 3 captions in the Rules; 0 in the Act; 3 yellow Change_Log rows). The only differences are the ones that were asked for: the L-8 provenance lines, the H-4 relative links, and the L-3 `IFERROR`. |
| **I-2** | All 79 commencement dates check out; no off-by-one. | Not re-checked this session. Taken from the audit. |
| **I-3** | `pip-audit`: no known vulnerabilities; every dependency pinned. | Not re-run this session. |
| **I-4** | Repository growth from the daily binary commits is about 1 KB/day — a non-issue. | Not re-measured. |
| **I-5** | `PRAGMA integrity_check` = ok; no NULL `full_text`. | Not re-run this session. |
| **I-6** | The real model behaved well on the cases a mock could not prove. | Not re-run — this session made **no** AI calls at all. |
| **I-7** | The "32 tests fail in some environments" mystery is an environment problem (missing PDF tooling), not a data problem. | Consistent with what was found here: `tests/test_legal_text_verbatim.py` now skips loudly when the PDF libraries are missing instead of failing without explanation. Those specific 32 failures were never reproduced on this machine, so this remains the audit's finding rather than one re-verified here. |

---

## What is still open

1. **The approval gate.** Options A, B and C are set out in the audit's §7 and in
   `CHANGELOG.md`. The audit recommends **C** (apply automatically, but mark the
   provision "UNCONFIRMED — awaiting review" in the Word and Excel output until a
   person confirms it). Not built — it is Gautam's and EY's decision.
2. **The four corrigendum phrase pairs (H-5) and the Seventh Schedule wording
   (H-7) need Gautam's approval** before the scripts are run with `--apply`.
3. **M-9** — revoke the old OpenRouter key, *then* delete its two lines from `.env`.
4. **H-1 / H-3** — create the healthchecks.io check, add the `HEARTBEAT_URL`
   secret, and confirm both workflows go green on GitHub.
5. **Follow-ups nobody has to do soon:** L-1, L-2, L-4, L-9, the two
   remaining Fifth Schedule run-in separator dashes, and teaching the discovery
   step's headless browser to use `certs/egazette-chain.pem` so the one remaining
   `ignore_https_errors=True` can go (it is alert-only and cannot change stored
   legal text, but it is the last one left).
