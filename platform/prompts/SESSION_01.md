# Session 1 — Interim approval fix (main) + backend skeleton (platform-build)

Read first: `CLAUDE.md`, `platform/SPEC.md` (§4, §5, §6), `platform/CHECKPOINT.md`,
`platform/prompts/_SESSION_RULES.md`. Follow the rules file for start/end of session.

## Why this session exists (plain words)
Gautam's approvals "keep coming back" because (a) the Excel is only a generated
report — nothing reads edits back into the database; (b) the database exists in
two copies (GitHub's, updated daily by the bot, and his PC's) and Git cannot
merge two edited copies of a SQLite file; (c) all 79 provisions and 142
change_log rows say `Pending Review`. Part A gives him a working way to approve
**on GitHub's copy** today. Part B starts the platform on a separate branch.

---

## Part A — on `main` (production). Keep changes small and safe.

Start: `git checkout main && git pull origin main` (the bot commits daily — always pull first).

Expected uncommitted files at the very start (added by Claude in Cowork on
28 Sep 2026 — they are the build plan, not stray changes): `CLAUDE.md`,
`platform/` (SPEC, CHECKPOINT, HOW_TO_RUN, prompts) and an appended entry in
`CHANGELOG.md`. Commit them first on `main` as "Add platform build plan and
session prompts" (pull first; if the pull conflicts with them, stop and ask).

**1.1 Investigate the "Excel with all pending approvals every run" report.**
Read `src/notify.py` (attachments are only added when regulatory changes were
applied), `src/export_excel.py`, `scripts/manual_dry_run_email_2026-09-23.py`, the
workflow, and `git log` of the bot's commits. Work out which email(s) Gautam is
actually getting with the Excel attached and why. Write the finding (plain words)
in the checkpoint session log. Fix only if it's clearly a bug; otherwise report.

**1.2 `scripts/review.py`** — the only supported way to record approvals until
the platform exists. Requirements:
- Flags: `--approve-changes CHG-0001,CHG-0002`, `--reject-changes ...`,
  `--confirm-provisions DPDPR-R7,...`, `--confirm-baseline` (all `change_origin='baseline'`
  rows → `Approved` and all provisions → `Confirmed`), `--approve-data-corrections`
  (all `data_correction` rows → `Approved`), `--by "Name"` (required),
  `--note "..."`, `--dry-run` (prints what would change, writes nothing).
- Sets `review_status`, `reviewed_by`, `review_date` (ISO date). Rejecting in this
  interim version only records the status + note — it does NOT revert text (that
  comes in Session 2); print a clear warning saying so.
- Unknown IDs → error, nothing written (all-or-nothing transaction).
- Prints a plain summary: counts before/after per status.
- Tests in `tests/test_review_script.py` using a temp copy of the DB.

**1.3 `.github/workflows/approve-changes.yml`** — manual "Run workflow" button
(`workflow_dispatch`) with inputs: `approve_change_ids`, `reject_change_ids`,
`confirm_provision_ids`, `confirm_baseline` (boolean), `approve_data_corrections`
(boolean), `reviewer` (required), `note`, `dry_run` (boolean, default false).
Steps: checkout, Python 3.12, install requirements, run `scripts/review.py` with
the inputs, regenerate Word + Excel (`src/export_word.py`, `src/export_excel.py`),
commit + push `db/dpdpa.db docs/*.docx data/*.xlsx` with message
"Approvals recorded by <reviewer> — <date>" (skip commit on dry run).
Add to BOTH this workflow and `daily-check.yml`:
```yaml
concurrency:
  group: dpdp-db-writes
  cancel-in-progress: false
```
so an approval and the daily run can never write at the same time. Don't change
anything else in `daily-check.yml`. Validate YAML (e.g. `python -c "import yaml; yaml.safe_load(open(...))"`).

**1.4 Make the Excel a clearly read-only report** (`src/export_excel.py`):
- First line of the README sheet, bold: "READ-ONLY REPORT — edits made in this
  file are NOT saved anywhere. To approve changes: GitHub → Actions → Approve
  changes → Run workflow."
- Remove the gold "human input" header styling and the dropdown validations on
  review columns; update the README sheet's colour legend and "How a change gets
  applied" text to describe the Approve-changes Action.
- Protect sheets without a password if openpyxl allows keeping sort/filter and
  hyperlinks working; if protection breaks either, skip protection and note it.
- Update any tests that assert the old gold styling; add a test for the banner.

**1.5 README.md**: add a short plain-language section "How to approve changes
(interim)" with the exact clicks on github.com, and a warning: never commit
`db/dpdpa.db` from the PC; always `git pull` before looking at the local copy.

**1.6 Ship Part A**: run the full test suite; show Gautam `git diff --stat` and a
plain summary; **ask for OK before `git push origin main`**. If he doesn't answer
in this session, leave it committed locally on `main`, mark 1.6 `[~]` with
"awaiting Gautam's OK to push", and continue with Part B (branch from local `main`).
Do NOT run the workflow with `confirm_baseline` — that is Gautam's decision (D5).

---

## Part B — on `platform-build`

**1.7** `git checkout -b platform-build` from the (updated) `main`. Update
`.gitignore`: `var/`, `frontend/node_modules/`, `frontend/.next/`, `.env*` but
keep `!.env.example`.

**1.8** `src/db.py`: `DB_PATH` = env `DPDP_DB_PATH` if set, else `db/dpdpa.db`
(identical behaviour when unset — production unaffected). Add a test.

**1.9 Backend skeleton** (`backend/`), per SPEC §3–§4:
- Check `python --version` (need ≥ 3.11). `backend/requirements.txt` with pinned
  current stable versions of: fastapi, uvicorn[standard], sqlalchemy (2.x),
  pydantic, pydantic-settings, python-multipart, httpx, apscheduler (3.x), pyjwt,
  argon2-cffi (or bcrypt), python-docx, openpyxl, python-pptx, pypdf (6.19.0 to
  match root), pdfplumber, pyyaml, pytest. Install with `python -m pip`.
- `app/config.py` (pydantic-settings, all SPEC §4 vars with dev defaults,
  paths resolved relative to repo root), `app/db/engines.py` (library/platform/
  tenant session factories; every connection sets foreign_keys, WAL, busy_timeout),
  `app/db/migrate.py` (numbered `.sql` runner + `schema_version`), `app/main.py`
  (FastAPI app, runs migrations on startup, `GET /api/health` returning DB
  paths' existence + schema versions + app version).
- `backend/tests/` with pytest config; tests use temp dirs, never `var/`.

**1.10 Library migration `001_platform_library.sql`** — additive only (SPEC §5.1):
`regulations` (+ seed 2 rows), `provision_regulation` (filled by prefix for all
existing provisions), `library_versions` (+ row version 1 "Initial baseline"),
`obligations`, `obligation_provisions`, `library_audit`. Must be safe to run
twice. Test: after migration, the existing `src/` tests still pass when
`DPDP_DB_PATH` points at a migrated temp copy.

**1.11 `python -m app.cli bootstrap-dev`** (run from `backend/`): creates `var/`
folders, copies `db/dpdpa.db` → `var/library.db` if absent (`--force` to
refresh), applies library migrations, creates empty `var/platform.db`. Prints what
it did. Test with temp paths. Run it once for real and record the health output
in the session log.

**1.12 Wrap up** per the rules file. In the CHANGELOG entry, explain Part A's
new approval button step by step for Gautam, and Part B in two or three sentences.

## Done when
Part A tests green and either pushed (with OK) or waiting on OK; `platform-build`
pushed with backend skeleton; `uvicorn app.main:app` starts and `/api/health`
answers; all existing tests still green.
