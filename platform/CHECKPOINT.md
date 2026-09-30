# Build checkpoint — DPDP Compliance Platform

> **Every Claude Code session reads this first and updates it after every task.**
> Legend: `[ ]` not started · `[~]` in progress / partly done · `[x]` done · `[!]` blocked (see Blockers)

## Now

- **Current session:** 1 (not started)
- **Branch for platform work:** `platform-build` (created in Session 1)
- **Next action:** Gautam merges branch `apply-data-fixes-2026-09-30` into `main`
  and pushes (the exact commands are at the end of the 30 Sep chat, and in
  `CHANGELOG.md`). After that, start Session 1 — run the prompt in
  `platform/prompts/SESSION_01.md`.
- **Last updated:** 2026-09-30 by Claude Code — platform work still not started. What
  happened instead: the independent audit of the existing `src/` pipeline was worked
  through on branch `audit-fixes-2026-09-30`. **All 4 Critical and all 7 High
  findings are addressed in code** — 9 fixed outright, and the last 2 (H-5, H-7)
  needed one-off scripts Gautam runs. **On 30 Sep 2026 he approved the wording and
  ran all four data-repair scripts with `--apply` against the real `db/dpdpa.db`.**
  The repaired database, the regenerated Word and Excel files, and the test changes
  that go with them are on branch **`apply-data-fixes-2026-09-30`** — committed,
  **not pushed and not merged**. What changed in the database, proved row by row
  against the pre-repair copy: `provisions.full_text` for DPDPR-SCH5/6/7 only
  (15 heading dashes + the Seventh Schedule wording), seven new `change_log` rows
  (CHG-0096…0098 `data_correction`, CHG-0099…0102 `regulatory`), four `source_log`
  rows set to `watched = 0`, and one new `source_snapshot` baseline for SRC-0001.
  Nothing else moved. Tests went 188 → 219 passing. Two of them are **not yet actually protecting
  anything**: H-1 (the heartbeat) does nothing until the healthchecks.io check
  exists and `HEARTBEAT_URL` is set, and H-3 (test CI) needs confirming green on
  GitHub after the merge. Finding by finding: `docs/audit_fixes_2026-09-30.md`.
  Narrative:
  `CHANGELOG.md` and `docs/audit_fixes_2026-09-30_session_report.md`. Order of
  everything done today: `docs/session_log_2026-09-30_audit_fixes.md`.
  That branch is **not pushed and not merged** — Gautam decides.
  Platform Session 1 is still the next thing to start.
- **Open, and waiting on Gautam:** (1) the approval-gate decision — options A/B/C,
  the audit recommends C; (2) ~~approving the four corrigendum phrase pairs (H-5) and
  the Seventh Schedule wording (H-7)~~ — **done 30 Sep 2026**, scripts applied;
  what remains is merging `apply-data-fixes-2026-09-30` into `main`;
  (3) revoke the old OpenRouter key, *then* delete its two lines from `.env` (M-9);
  (4) create the healthchecks.io check and add the `HEARTBEAT_URL` secret (H-1).
- **Open, technical, nobody has to do soon:** the "apply new documents oldest-first"
  engine; MeitY's HTTP 403 on its own listing pages; PIB's 20-item, dateless feed;
  the discovery step's headless browser still using `ignore_https_errors=True`
  (alert-only, cannot change stored legal text, but it is the last one left);
  audit L-1, L-2, L-4, L-9; the two remaining Fifth Schedule run-in dashes.

## Session 1 — Interim approval fix + backend skeleton

Part A (on `main`, push only after Gautam's OK)
- [ ] 1.1 Investigate why the emailed Excel shows everything as pending (read notify.py, export_excel.py, scripts/manual_dry_run_email_2026-09-23.py); write findings in the session log
- [ ] 1.2 `scripts/review.py` (approve/reject/confirm/baseline, dry-run, reviewer required) + tests
- [ ] 1.3 `.github/workflows/approve-changes.yml` (manual run button) + shared `concurrency` group added to `daily-check.yml`
- [ ] 1.4 Excel made read-only (banner, no gold input columns/dropdowns, README sheet text) + tests updated
- [ ] 1.5 Plain-language "How to approve now" section in README.md; CHANGELOG entry
- [ ] 1.6 Full test suite green; diff shown to Gautam; pushed to `main` after OK (or committed locally + noted if no OK yet)

Part B (on `platform-build`)
- [ ] 1.7 Branch `platform-build` created from updated `main`; `.gitignore` adds `var/`, `frontend/node_modules/`, `frontend/.next/`, `.env*` except `.env.example`
- [ ] 1.8 `src/db.py` honours `DPDP_DB_PATH` (default unchanged) + test
- [ ] 1.9 `backend/` skeleton: config.py, engines.py, migrate.py, main.py with `/api/health`, requirements.txt pinned
- [ ] 1.10 Library migration 001 (regulations, provision_regulation, library_versions v1, obligations, obligation_provisions, library_audit) — additive only
- [ ] 1.11 `python -m app.cli bootstrap-dev` copies `db/dpdpa.db` → `var/library.db`, applies migrations; tests prove existing `src/` pipeline tests still pass against the migrated copy
- [ ] 1.12 Session wrap-up (checkpoint, CHANGELOG, commit, push branch)

## Session 2 — Platform DB, auth, LLM layer, approvals, pipeline runner
- [ ] 2.1 Platform migrations (users, consultant_assignments, tenants, jobs, llm_calls, platform_audit)
- [ ] 2.2 Auth: hashing, JWT cookie login/logout/me, role dependencies, `create-admin` CLI, login rate limit + tests
- [ ] 2.3 LLM layer: interface, mock, OpenRouter client (200-with-error handling, retries, ZDR, cost log, spend cap) + tests
- [ ] 2.4 Classifier can use OpenRouter behind `CLASSIFIER_PROVIDER` (default `anthropic`, production unchanged) + tests
- [ ] 2.5 `apply_change.py` on branch: regulatory → Pending Review; data_correction → auto Approved; email/Excel wording updated + tests
- [ ] 2.6 Approval services: approve / reject-with-span-reversal / bulk confirm / publish library version / audit + tests
- [ ] 2.7 Admin API: list/detail(with word diff)/approve/reject/bulk, versions, provisions confirm + tests
- [ ] 2.8 Pipeline runner + APScheduler job (off by default), job rows recorded + tests
- [ ] 2.9 Session wrap-up

## Session 3 — Obligations checklist
- [ ] 3.1 Obligation services + admin API (list, detail, edit, set status, publish → new version) + tests
- [ ] 3.2 `applicability.yaml` questionnaire draft + loader + tests
- [ ] 3.3 `scripts/platform/draft_obligations.py` (mock first; verbatim excerpt check; severity/commencement rules; cost cap)
- [ ] 3.4 Real drafting run on dev DB within cap; results + cost logged
- [ ] 3.5 Coverage report `docs/platform/obligation_coverage.md` + read-only review workbook for EY legal
- [ ] 3.6 Propagation part 1: approving a change flags linked obligations `Needs Review` + tests
- [ ] 3.7 Session wrap-up

## Session 4 — Tenants and knowledge-base ingestion
- [ ] 4.1 Tenant migrations + tenant service (create, list, archive, export zip, erase) + tests
- [ ] 4.2 `require_tenant_access` + test that enumerates all tenant routes for cross-tenant denial
- [ ] 4.3 Questionnaire answers API → applicable obligations list + tests
- [ ] 4.4 Upload API, type/size checks, sha256 dedupe, extraction per format, failure surfaced + tests
- [ ] 4.5 Chunking with locations + FTS5 index + search helper + tests
- [ ] 4.6 Redaction utility + tests
- [ ] 4.7 Fictional test client fixtures (clearly marked FICTIONAL) with deliberate gaps + expected labels file
- [ ] 4.8 Session wrap-up

## Session 5 — Mapping engine and propagation
- [ ] 5.1 Jobs worker (in-process) + tests
- [ ] 5.2 Retrieval + mapping service + quote verification + downgrade rules + cache + spend cap + tests (mock)
- [ ] 5.3 Assessments API, consultant confirm/override, history + tests
- [ ] 5.4 Actions (auto-draft for gaps) + API + tests
- [ ] 5.5 Propagation part 2 (alerts on pending change; stale + re-map on new version) + tests
- [ ] 5.6 Accuracy check on fictional client: mock + one real run within cap; agreement % recorded
- [ ] 5.7 Session wrap-up

## Session 6 — Frontend foundation + EY admin console
- [ ] 6.1 Node check; Next.js app scaffolded (TS, Tailwind, Recharts), `/api` rewrite to backend
- [ ] 6.2 Login, session handling, role-based layout, disclaimer footer
- [ ] 6.3 Admin: approvals queue + change detail (word diff) + approve/reject/bulk
- [ ] 6.4 Admin: library versions, obligations list/edit/publish
- [ ] 6.5 Admin: tenants list/create, consultant assignment, mapping review screen
- [ ] 6.6 `npm run lint` + `npm run build` green; screenshots or notes in session log
- [ ] 6.7 Session wrap-up

## Session 7 — KPIs and client dashboard
- [ ] 7.1 KPI service + endpoints + weekly snapshots + tests with hand-computed values
- [ ] 7.2 Client dashboard page (headline tiles, heatmap, deadlines, exposure, updates, coverage, remediation, freshness, trend)
- [ ] 7.3 Obligation drill-down, documents page (upload/status), actions page
- [ ] 7.4 Board-pack export (Excel + print-friendly page)
- [ ] 7.5 lint/build/tests green
- [ ] 7.6 Session wrap-up

## Session 8 — Hardening, deployment prep, rehearsal
- [ ] 8.1 Security pass (isolation, cookies, rate limit, uploads, `pip-audit`, `npm audit`) — findings fixed or listed
- [ ] 8.2 SQLite WAL/busy_timeout confirmed; backup + restore script tested
- [ ] 8.3 Dockerfiles, docker-compose, `.env.example`
- [ ] 8.4 CI workflow for `platform-build`
- [ ] 8.5 End-to-end rehearsal script with a simulated law change; results logged
- [ ] 8.6 `deploy/RUNBOOK.md` (deploy, cutover checklist, backups, onboarding playbook) + README update
- [ ] 8.7 `platform/PR_DESCRIPTION.md` for merging `platform-build` → `main`
- [ ] 8.8 Final wrap-up: list of decisions only Gautam/EY can take

## Open decisions (defaults used until Gautam decides)

| # | Decision | Default being used | Status |
|---|---|---|---|
| D1 | Approval model: alert immediately, score only after approval | Adopted as in SPEC §6 | Proposed 28 Sep, awaiting Gautam |
| D2 | Hosting environment (likely EY Azure) | Build with Docker, runs anywhere; no deployment | Awaiting EY IT |
| D3 | Can client documents go to an LLM via OpenRouter (ZDR)? | Only fictional data used; redaction on; `mock` default | Awaiting EY Risk |
| D4 | Who at EY legal reviews obligations; pilot client | Obligations stay Draft (dev-publish only in `var/`) | Open |
| D5 | Bulk-confirm the 79 baseline provisions | **DONE 2026-09-29** — Gautam reviewed everything; all 79 provisions set to `Confirmed` and all 142 change-log rows to `Approved` directly in `db/dpdpa.db` (one-off SQL, not via the planned Approve-changes Action). Excel regenerated. | Closed. Session 1 Part A (`scripts/review.py`, Approve-changes Action) is still needed for FUTURE approvals. |
| D6 | Commencement: 13 vs 14 Nov | `DEADLINE_DATES` default uses 13th | Open (legal question) |
| D7 | Switch daily classifier from Anthropic to OpenRouter | Supported, default stays `anthropic` | Gautam decides |

## Spec change requests
_(Claude Code: add rows here instead of silently changing the design.)_

| Date | Session | Request | Why | Gautam's answer |
|---|---|---|---|---|

## Blockers
_(none yet)_

## Session log

| Date | Session | What was done (plain words) | Tests | Commits / branch | AI spend |
|---|---|---|---|---|---|
| 2026-09-28 | 0 (Cowork) | Created SPEC, CHECKPOINT, CLAUDE.md and session prompts. No code changed. | — | not committed | $0 |
| 2026-09-29 | manual (Cowork) | Gautam finished reviewing everything. Set all 79 provisions to `Confirmed` and all 142 change-log rows to `Approved` (reviewer: Gautam Kundalia, date 2026-09-29), then rebuilt `data/DPDP_Rules_Tracker.xlsx` from the database. No legal text, summaries or source data changed. Closes decision D5. No code changed. | Not re-run for this change (data-only); the same 32 PDF-extraction tests fail before and after (see CHANGELOG) | commit on `main` | $0 |
| 2026-09-30 | manual | Detection coverage: new-document discovery (eGazette search, alert-only, never touches provisions/change_log). Built, tested, merged to `main`, then three real GitHub Actions timeouts diagnosed and fixed (see CHANGELOG). Confirmed working in production: a real daily run completed with zero errors and correctly captured its first-ever baseline. MeitY's own document-list pages investigated and confirmed genuinely blocked (not built); PIB investigated as a second discovery source and ruled out (not built). | 76 passed (64 baseline + 12 new), zero new failures, re-confirmed after every fix | commits `76f9fdb`..`fdd8686` on `main` (merged from branch `detection-coverage-fix`) | $0 |
| 2026-09-30 | manual (audit fixes, part 1) | Fixed the four **critical** findings from the independent audit of `6022d45`. C-1: the Act verbatim guard rebuilt its text from the PDF and then checked that, so it could never fail — it now reads the database. C-2: the Rules guard's fallback only asked whether a passage's words appeared *somewhere* in the PDF, ignoring order, so `shall`→`may` and `six months`→`six years` both passed — replaced with an ordered comparison, and the 28 genuine differences are now exact reviewed pairs that expire by themselves. C-3: the DPDP Rules PDF (SRC-0001, the most important document here) had no baseline, so the first real amendment would have been stored as the baseline and reported as "No change detected" — baselines are now written when a source is first recorded, and a missing one is a loud error. C-4: any watched page could get text written into `provisions.full_text` (the audit proved it with a forged notice) — each source now has an explicit `may_amend` list, enforced in two places, failing closed; PIB is alert-only with no AI call, and the eGazette home page is retired (100% false-positive rate, an AI call a day for nothing). TLS verification is no longer disabled for any host. Also wrote the two one-off repair scripts that error messages already pointed at but which did not exist, and corrected several README claims that had become untrue. **This probably also settles the 32 PDF-extraction test failures noted in the 29 Sep row** — that test file now skips with a clear reason when the PDF-reading libraries are missing, instead of failing without explanation, which is the most likely cause of those 32. Not confirmed: those specific 32 failures were never reproduced, so this is a reasonable expectation rather than a checked fact. | 176 passed (76 baseline + 100 new), zero failures | 7 commits on branch `audit-fixes-2026-09-30` — **not pushed, not merged** (Gautam's call) | $0 |
| 2026-09-30 | manual (audit fixes, part 2: verify + finish) | Checked commit `4e445cf` line by line against its own session prompt, because the session before this one committed it as work-in-progress and said plainly that nobody had. Two problems found. (1) A real break: `python src/export_excel.py` crashed on the committed database with "no such column: watched" — the new column is added by a migration only `run_pipeline.py` applied, and regenerating the tracker by hand is exactly what the hand-over asks Gautam to do. (2) The test for that column re-typed the exporter's own query and checked that, so deleting the filter from the exporter left all 176 tests green. Both fixed; the old-database upgrade test the project's rules require was added too. Everything else in `4e445cf` held up — each fix proven by putting the old behaviour back in a throwaway worktree and watching the new test fail. The acceptance test was re-derived from scratch: regenerating from today's committed database with `main`'s code and with this branch's gives identical body text and identical highlighting (4 yellow spans, 3 strike-throughs, 3 captions, 3 yellow Change_Log rows); the only differences are the three that were asked for. Then finished what Session 3 never reached: the two data-repair scripts (H-5 corrigendum items recorded as government changes; H-7/M-11 verbatim wording restored), the complete finding-by-finding table for every audit finding, and the README / Excel README sheet / CLAUDE.md corrections. **The four corrigendum phrase pairs and the Seventh Schedule wording still need Gautam's approval before `--apply`.** | 176 -> 198 passing, zero failures; 5-mutation spot-check all caught | 3 commits on `audit-fixes-2026-09-30` (`c3828c6`, `4e42aa0`, `b1e8cf4`) plus this one — **not pushed, not merged** | $0 |
| 2026-09-30 | manual (apply data fixes + make the tests understand the repaired database) | Gautam ran the four repair scripts with `--apply` on the real `db/dpdpa.db`, and `pytest` went from 0 failures to 11. None of the 11 was a fault in the repair. (a) Eight tests started from a copy of the live database, which was now already repaired, so the scripts they were meant to observe correctly did nothing; three of those eight had in fact broken slightly earlier, when the **daily bot's own commit `7601d1e`** added the `watched` column to the committed database — not from the repair at all. Fixed with a committed fixture, `tests/fixtures/dpdpa_pre_repair.db` (from `83207c2`, the last commit before both), so the starting point can never drift again. This also fixed a test that could not fail: `test_the_three_scripts_run_together_in_order` was green only because its numbers were already true of the repaired database. (b) Two tests named reviewed exceptions that the repair had made obsolete; 16 were deleted and 2 deliberately kept (the Fifth Schedule run-in dashes are still genuinely missing and still open). Deleting the Seventh Schedule entry mattered: while it existed the guard **excused** that paraphrase, so a new regression test could not have worked. (c) One real problem — `seed_rules` still produced the old wording, so re-seeding would have silently undone the repair; the three rows were re-dumped into `data/rules_verbatim_2026-09-23.json` straight from the repaired database, not retyped. Also verified the repair itself table-by-table against `git show HEAD:db/dpdpa.db`, and read the regenerated Word/Excel rather than trusting the exporters' own summary. **Honest limitation written down:** the PDF guard cannot catch a missing heading dash and never could — its fallback deliberately allows punctuation-only differences — so those 15 dashes are protected by a plain presence test and by the seeding comparison, not by the guard. | 188 -> 219 passing, zero failures; 6 mutations applied and all caught | 2 commits on `apply-data-fixes-2026-09-30` — **not pushed, not merged** | $0 |
