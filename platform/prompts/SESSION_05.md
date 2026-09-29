# Session 5 — Mapping engine, consultant review, actions, change propagation

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§5.3, §10,
§11), `platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`.
AI spend allowed: **$1.00** (task 5.6 real run only, fictional client only).

## Goal (plain words)
The core of the product: for each obligation that applies to a client, find the
relevant passages in their documents and ask the AI "does this meet the
obligation? quote the proof". Code then checks the quote really exists. EY
consultants confirm or correct the result, gaps become to-do actions, and when
the law changes only the affected items are re-checked.

## Tasks

**5.1 Jobs worker** (`app/services/jobs.py`): `enqueue(kind, tenant_id, payload)`,
an in-process worker (background thread started in `main.py` lifespan; also
`python -m app.cli work --once` for tests/CLI) that claims one `queued` job at a
time atomically, runs its handler, stores `result`/`error`. A crash → `failed`
with the traceback tail (never silently re-queued forever; max 2 retries).
Move document extraction (Session 4) onto a job `ingest_document`. Tests.

**5.2 Mapping service** (`app/services/mapping.py`) per SPEC §10, job kind
`map_obligations` with payload `{obligation_ids: [...] | "all_applicable"}`:
retrieval (Session 4 `search`, query = keywords + title), redaction before the
LLM (when `REDACT_BEFORE_LLM`), prompt with the obligation's requirement text,
evidence_expected and the numbered chunks; JSON schema output; **verbatim quote
check against the un-redacted chunk text** (map placeholders back or compare
with placeholders normalised — design this carefully and test it); downgrade
rules; cache key; spend cap → remaining items `Not assessed` + job result says
how many were skipped and why; history rows. Keep the prompt in one file
(`app/services/prompts/mapping.md`) so EY can read it. Tests with the mock for
every branch: valid quote, fake quote, partial, insufficient evidence
(both confidence cases), cap reached, EY-verified row not overwritten.

**5.3 Assessments API** (`app/api/tenant_assessments.py`): `POST
/api/tenants/{tenant_id}/mapping/run` (EY roles; enqueues job; returns job id),
`GET /api/jobs/{job_id}` (scoped to tenant), `GET .../assessments?status=&topic=&stale=`,
`GET .../assessments/{obligation_id}` (with evidence, chunk text, document
location, history), `POST .../assessments/{obligation_id}/review` (EY roles:
confirm or override status + comment → `ey_verified`). Tests.

**5.4 Actions** (`app/services/actions.py`, `app/api/tenant_actions.py`): after
mapping, create a draft action for each Gap/Partial without one (title from
`missing_elements`); CRUD for contributors/EY; overdue = past due and not done. Tests.

**5.5 Propagation part 2** (`app/services/propagation.py`) per SPEC §11:
- Hook in the pipeline path: after each run (runner, Session 2), for every new
  `Pending Review` regulatory change, add `update_under_review` alerts to tenants
  with an applicable obligation linked to that provision.
- On `publish_version`: for new/changed/retired obligations, per tenant where
  applicable: mark assessments `stale=1` (or insert `Not assessed`), add
  `reassessment` alerts, enqueue `map_obligations` for exactly those ids;
  `update_approved` alerts for approved changes.
- EY-verified rows are marked stale, never overwritten automatically.
- Tests: simulate a change to one provision end-to-end on temp DBs and assert
  only its obligations are re-queued.

**5.6 Accuracy check (Gate 3 metric)**: `scripts/platform/evaluate_mapping.py`
runs mapping for the fictional client and compares with `expected_labels.yaml`:
exact-status agreement %, "gap caught" recall (how many deliberate gaps the AI
flagged), and fake-quote rejections. Run once with the mock (plumbing) and once
for real via OpenRouter within $1.00. Write results to
`docs/platform/mapping_accuracy_<date>.md` in plain words (what the numbers mean,
where the AI was wrong, prompt changes tried). Do not tune the prompt more than
2 rounds this session; record ideas instead.

**5.7 Wrap up** per the rules file. CHANGELOG: explain the mapping flow, the
quote check, what the accuracy numbers mean, cost, and that the "agreed rate"
for Gate 3 is Gautam/EY's call.

## Done when
Fictional client fully mapped (mock and real), accuracy report committed,
consultant review works via API, a simulated law change re-queues only affected
obligations, all tests green, branch pushed.
