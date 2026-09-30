# Build checkpoint — DPDP Compliance Platform

> **Every Claude Code session reads this first and updates it after every task.**
> Legend: `[ ]` not started · `[~]` in progress / partly done · `[x]` done · `[!]` blocked (see Blockers)

## Now

- **Current session:** 1 (not started)
- **Branch for platform work:** `platform-build` (created in Session 1)
- **Next action:** Start Session 1 — run the prompt in `platform/prompts/SESSION_01.md`.
- **Last updated:** 2026-09-30 by Claude Code — platform work still not started. What
  happened instead: the four critical findings from the independent audit of the
  existing `src/` pipeline were fixed on branch `audit-fixes-2026-09-30` (see the
  session log at the bottom and `CHANGELOG.md`). That branch is **not pushed and
  not merged** — Gautam decides. Platform Session 1 is still the next thing to start.

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
| 2026-09-30 | manual (audit fixes, part 1) | Fixed the four **critical** findings from the independent audit of `6022d45`. C-1: the Act verbatim guard rebuilt its text from the PDF and then checked that, so it could never fail — it now reads the database. C-2: the Rules guard's fallback only asked whether a passage's words appeared *somewhere* in the PDF, ignoring order, so `shall`→`may` and `six months`→`six years` both passed — replaced with an ordered comparison, and the 28 genuine differences are now exact reviewed pairs that expire by themselves. C-3: the DPDP Rules PDF (SRC-0001, the most important document here) had no baseline, so the first real amendment would have been stored as the baseline and reported as "No change detected" — baselines are now written when a source is first recorded, and a missing one is a loud error. C-4: any watched page could get text written into `provisions.full_text` (the audit proved it with a forged notice) — each source now has an explicit `may_amend` list, enforced in two places, failing closed; PIB is alert-only with no AI call, and the eGazette home page is retired (100% false-positive rate, an AI call a day for nothing). TLS verification is no longer disabled for any host. Also wrote the two one-off repair scripts that error messages already pointed at but which did not exist, and corrected several README claims that had become untrue. **This also fixes the 32 PDF-extraction test failures noted in the 29 Sep row** (they now skip with a clear reason when the PDF libraries are missing, instead of failing mysteriously). | 176 passed (76 baseline + 100 new), zero failures | 7 commits on branch `audit-fixes-2026-09-30` — **not pushed, not merged** (Gautam's call) | $0 |
