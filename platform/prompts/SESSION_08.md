# Session 8 — Hardening, deployment prep, end-to-end rehearsal

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§13, §14,
§15), `platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`.
AI spend allowed: **$0** (rehearsal uses the mock). **Do not deploy anything,
change GitHub secrets, push `main` or merge** — this session prepares; Gautam decides.

## Goal (plain words)
Make the platform safe and ready to hand over: check security, make backups
work, package it so any approved server can run it, prove the whole flow works
end to end including a pretend law change, and write the instructions Gautam
and EY IT will follow.

## Tasks

**8.1 Security pass**: review auth (cookie flags per environment, JWT secret
required in prod, rate limit), tenant isolation test still covers every route,
upload handling (type sniffing not just extension, size, path traversal in
filenames, zip bombs for docx/xlsx/pptx), error responses leak no stack traces
in prod mode, audit rows for sensitive actions. Run `python -m pip install
pip-audit && pip-audit -r backend/requirements.txt` and `npm audit` — fix what's
safe, list the rest. Write `docs/platform/security_review_<date>.md`.

**8.2 SQLite robustness**: confirm WAL + busy_timeout on every connection (test);
`deploy/backup.py` — online `.backup` of library, platform and every tenant DB to
`var/backups/<date>/`, 14-day retention, plus `restore.py`; a test that backs up,
deletes, restores and compares row counts.

**8.3 Packaging**: `deploy/Dockerfile.backend`, `deploy/Dockerfile.frontend`,
`deploy/docker-compose.yml` (one `var` volume, health checks, restart policy,
env from `.env`), `.env.example` with every SPEC §4 variable and a comment each.
If Docker isn't available locally, validate files by inspection and note it —
don't install Docker.

**8.4 CI**: `.github/workflows/ci.yml` — on push/PR to `platform-build`: root
pytest, backend pytest, frontend lint + build. No secrets needed (mock LLM).
Must not touch or trigger `daily-check.yml` / `approve-changes.yml`.

**8.5 End-to-end rehearsal** `scripts/platform/e2e_rehearsal.py` on a fresh temp
`var/`: bootstrap → create admin → dev-publish obligations → create fictional
tenant + consultant + client user → questionnaire → upload fixtures → mapping
(mock) → consultant confirms 3 items → dashboard numbers → **simulate a law
change** (feed a fake changed source through the real pipeline code path with a
fake fetcher, so `apply_change` writes a Pending Review amendment to a provision
linked to an applicable obligation) → client sees "update under review", score
unchanged → admin approves, edits obligation, publishes version N+1 → affected
assessment marked stale and re-mapped → dashboard reflects it. Assert each step.
Write results to `docs/platform/e2e_rehearsal_<date>.md`.

**8.6 Documentation**: `deploy/RUNBOOK.md` in plain language — run locally;
deploy to a Linux VM (e.g. EY Azure, pending EY IT approval) with Docker;
the cutover checklist from SPEC §13 as tick-boxes with exact commands and a
rollback step for each; nightly backups; onboarding playbook for a new client
(create tenant → users → questionnaire → uploads → mapping → consultant review →
publish dashboard); how to rotate secrets; what to do if the daily monitor
fails. Update root `README.md` with a short "Platform" section linking to it.

**8.7 PR description** `platform/PR_DESCRIPTION.md` for `platform-build` → `main`:
what changes, what goes live at merge (notably: regulatory changes become
Pending Review), pre-merge checklist (cutover done first), test evidence.

**8.8 Final wrap-up** per the rules file. In the checkpoint and CHANGELOG, list
clearly what only Gautam/EY can now do: EY IT hosting approval (D2), EY Risk on
client data + LLM (D3), EY legal sign-off of obligations (D4), pilot client
consent in writing, baseline confirm (D5), classifier provider (D7), and the
cutover + merge.

## Done when
Security review written, backups tested, Docker/CI files in place, rehearsal
passes end to end, RUNBOOK and PR description written, all tests green, branch
pushed, checkpoint says "Build complete — awaiting decisions".
