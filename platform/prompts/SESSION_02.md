# Session 2 — Platform DB, login & roles, LLM layer, approvals, pipeline runner

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§4, §5.2,
§6, §10 item 7, §14), `platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`.
AI spend allowed this session: **$0.20** (one optional real OpenRouter smoke call). Everything else uses the mock.

## Goal (plain words)
Give the backend its own user accounts and roles, one safe way to call AI models
(through OpenRouter, as EY requires), and — most importantly — the real approval
flow: changes arrive as "Pending Review" and an EY admin approves or rejects
them through the API, in one place, with a record of who did what.

## Tasks

**2.1 Platform migrations** (`migrations/platform/001_*.sql`): `users`,
`consultant_assignments`, `tenants`, `jobs`, `llm_calls`, `platform_audit` per
SPEC §5.2, plus ORM models in `app/models/platform.py`. Tests.

**2.2 Auth & roles** (`app/security/`, `app/api/auth.py`):
- Password hashing (argon2 or bcrypt), `POST /api/auth/login` (sets httpOnly JWT
  cookie, 8 h), `POST /api/auth/logout`, `GET /api/auth/me`.
- Dependencies: `current_user`, `require_role(*roles)`; `require_tenant_access`
  stub that Session 4 completes (for now: EY roles pass; client roles checked
  against `users.tenant_id`).
- Simple in-memory login rate limit (e.g. 10 failures / 15 min per email+IP).
- CLI: `python -m app.cli create-admin --email ... --name ...` (prompts for password; never prints it).
- Tests: good/bad login, expired token, role denial, rate limit.

**2.3 LLM layer** (`app/llm/`):
- `base.py`: interface `complete_json(system, user, schema, purpose, tenant_id=None) -> dict`
  returning parsed JSON + usage.
- `mock.py`: deterministic, driven by registered canned responses (tests register them).
- `openrouter.py`: httpx; model from `OPENROUTER_MODEL`; temperature 0; JSON
  output; send ZDR / no-data-collection provider preferences when
  `OPENROUTER_ZDR=true` — **check the current OpenRouter API docs for the exact
  request fields** and cite the doc URL in a code comment. Treat HTTP 200 bodies
  that contain `"error"` as failures (Sept 2026 lesson: OpenRouter wraps upstream
  provider errors in a 200). Retry 3× with backoff; raise with the real message.
- `costs.py`: record every call in `llm_calls`; enforce `LLM_MAX_USD_PER_RUN`
  with a `SpendCapReached` exception raised *before* the call that would exceed it.
- Tests with `httpx.MockTransport` for: success, 200-with-error, 5xx retry,
  malformed JSON, spend cap. Optionally one real smoke call (≤ $0.20) if
  `OPENROUTER_API_KEY` is in `.env`; log the cost.

**2.4 Daily classifier via OpenRouter (optional path).** In `src/classify_change.py`,
add a provider switch `CLASSIFIER_PROVIDER` (`anthropic` default = today's exact
behaviour; `openrouter` = same prompt and output schema via OpenRouter JSON mode,
with the same validation). Keep `src/` free of imports from `backend/` — put a
small `src/llm_gateway.py` in `src/` if needed. All existing classifier tests
must pass unchanged; add tests for the OpenRouter path with mocks. Do not change
the GitHub workflow's env.

**2.5 Pending Review for regulatory changes (branch only).** In
`src/apply_change.py`: `regulatory` rows → `review_status='Pending Review'`,
`reviewed_by=NULL`, `review_date=NULL`, note "Awaiting EY approval". (Text is
still applied to `provisions` immediately, per SPEC §6.) Update `notify.py`
wording ("N changes detected — pending EY approval") and the Excel README text.
Update/extend tests. This only goes live at cutover; production on `main` is untouched.

**2.6 Approval services** (`app/services/approvals.py`, `versions.py`):
- `approve(change_ids, by, note, checked_obligations=False)` — enforce the tiering
  in SPEC §6 (refuse Amendment/Repeal/New Provision or confidence < 0.9 unless
  `checked_obligations=True`).
- `reject(change_ids, by, note)` — reverse the text span: replace `new_full_text`
  with `old_full_text` in the provision only if it occurs exactly once; for a
  rejected `New Provision` set provision `status='Draft'` + note; for a rejected
  `Repeal` restore `status='Active'`. If reversal is impossible, raise and write
  nothing. Tests for each case.
- `confirm_provisions(ids | all_baseline, by)`.
- `publish_version(by, note, change_ids, obligation_ids) -> version` — new
  `library_versions` row; audit rows in `library_audit`.
- All in single transactions; tests on a temp migrated copy of the real DB.

**2.7 Admin API** (`app/api/admin_changes.py`, `admin_library.py`), `ey_admin` only
(`ey_consultant` may read):
`GET /api/admin/changes?status=&origin=&page=`, `GET /api/admin/changes/{id}`
(includes a word-level diff — reuse `src/word_diff.py` if suitable),
`POST /api/admin/changes/approve`, `POST /api/admin/changes/reject` (bulk, with
note), `GET /api/admin/library/versions`, `POST /api/admin/library/publish`,
`POST /api/admin/provisions/confirm`. Pydantic request/response models. Tests.

**2.8 Pipeline runner** (`app/pipeline/runner.py`, `scheduler.py`):
- `python -m app.cli run-pipeline` runs `src/run_pipeline.py` as a subprocess
  with `DPDP_DB_PATH` = library DB and `NOTIFY_ENABLED` respected (skip email
  when false — add that switch to `src/notify.py`/`run_pipeline.py` with default
  = send, so production is unchanged). Records a `jobs` row with exit code and
  captured output tail. Non-zero exit → job `failed` with the error (never hidden).
- APScheduler job at `PIPELINE_CRON_IST` when `SCHEDULER_ENABLED=true`.
- Tests with a fake pipeline script. Do not hit government sites in tests.

**2.9 Wrap up** per the rules file. In CHANGELOG, explain: how approval now
works on the branch, what "Pending Review" means now, and that production is unchanged until cutover.

## Done when
On a dev DB: create an admin via CLI → log in via API → list pending changes →
approve one and reject one (with text reversal) → publish version 2 → audit rows
exist. All tests green. Branch pushed.
