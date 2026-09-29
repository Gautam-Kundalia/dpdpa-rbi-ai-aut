# DPDP Compliance Platform — Build Specification

Version 1.0 · written 28 Sep 2026 · owner: Gautam Kundalia (EY)
Source plan: Claude Doc "DPDP Compliance Platform — Plan of Action"
(https://claude.ai/code/artifact/79a69b16-a71e-4dea-85fc-43a404a096ef).

This file is the **design to build to**. It changes only through the "Spec
change requests" list in `platform/CHECKPOINT.md`, which Gautam approves.

---

## 1. What we are building (plain words)

Today: a daily script checks government websites for changes to the DPDP Act
and Rules, stores the law word-for-word in SQLite (`db/dpdpa.db`) and emails a
summary. It runs on GitHub Actions.

Target: one web platform that EY runs for **many clients**:

1. A shared **law library** that EY maintains (the existing database, plus a
   new checklist of **obligations** — the specific things a company must do).
2. A private space per **client** (a "tenant"), where the client's own policies
   and procedures (their "knowledge base") are uploaded and automatically
   checked against the obligations.
3. **Dashboards** showing each client where they comply and where they have
   gaps, updated whenever the law changes.
4. An **EY admin console** where law changes are approved in one click, so an
   approval is made once, in one place, and reaches every client.

Org-mandated stack: **FastAPI** (backend), **SQLite** (databases),
**Next.js** (frontend), **OpenRouter** (all LLM calls for the platform).

## 2. Architecture

```
Government sources ──► Daily monitor (existing src/ pipeline, run by the backend's scheduler)
                                   │ writes changes as "Pending Review"
                                   ▼
                        library.db  (shared law library + obligations)
                                   ▲
OpenRouter (LLM) ◄──►  FastAPI backend (backend/)  ◄──►  Next.js web app (frontend/)
                                   │                        ├─ EY admin console
                                   ▼                        └─ Client dashboards
                   platform.db (users, tenants, jobs, LLM cost log)
                   tenants/<slug>.db (one SQLite file per client) + uploads/<slug>/
```

- **One server, one master copy.** In production all databases live on one
  EY-hosted server (hosting not yet approved — build so it runs anywhere with
  Docker). GitHub holds code only after cutover (Section 13).
- **The backend is the only writer** to the databases. The frontend only talks
  to the backend's HTTP API.
- **Existing `src/` pipeline is reused, not rewritten.** The backend runs it
  against the library database path given by env var `DPDP_DB_PATH`.

## 3. Repository layout (target)

```
backend/
  app/
    main.py                 FastAPI app, routers, startup (migrations, scheduler)
    config.py               pydantic-settings; all env vars below
    cli.py                  python -m app.cli <command>  (create-admin, bootstrap-dev, run-pipeline, ...)
    db/
      engines.py            session factories: library, platform, tenant(slug)
      migrate.py            minimal numbered-SQL migration runner (schema_version table)
      migrations/library/NNN_*.sql
      migrations/platform/NNN_*.sql
      migrations/tenant/NNN_*.sql
    models/                 SQLAlchemy 2.0 ORM models: library.py, platform.py, tenant.py
    security/               passwords, JWT cookie, dependencies (require_role, require_tenant_access)
    llm/                    base.py (interface), openrouter.py, mock.py, costs.py
    services/               approvals.py, versions.py, obligations.py, propagation.py,
                            tenants.py, ingestion.py, redaction.py, retrieval.py,
                            mapping.py, actions.py, kpis.py, exports.py, jobs.py
    pipeline/               runner.py (runs src/run_pipeline.py against DPDP_DB_PATH), scheduler.py
    api/                    health.py, auth.py, admin_changes.py, admin_library.py,
                            admin_obligations.py, admin_tenants.py, tenant_profile.py,
                            tenant_documents.py, tenant_assessments.py, tenant_actions.py,
                            tenant_dashboard.py, tenant_exports.py
    config_data/applicability.yaml   the applicability questionnaire
  tests/                    pytest; fixtures/ holds the FICTIONAL test client only
  requirements.txt          pinned
frontend/                   Next.js (App Router, TypeScript, Tailwind, Recharts)
deploy/                     Dockerfiles, docker-compose.yml, backup script, RUNBOOK.md
platform/                   SPEC.md, CHECKPOINT.md, HOW_TO_RUN.md, prompts/
scripts/platform/           one-off/admin scripts (draft_obligations.py, e2e_rehearsal.py, ...)
var/                        GIT-IGNORED runtime data: library.db, platform.db, tenants/, uploads/, backups/
src/, db/, docs/, data/     existing pipeline — keep working; do not restructure
```

## 4. Configuration (env vars; `.env` locally, `.env.example` committed)

| Var | Meaning | Default (dev) |
|---|---|---|
| `DPDP_DB_PATH` | Library DB used by `src/` pipeline AND backend. `src/db.py` must honour it (falls back to `db/dpdpa.db` so production is unchanged) | `var/library.db` for backend |
| `PLATFORM_DB_PATH` | Platform DB | `var/platform.db` |
| `TENANTS_DIR` | Folder of per-client DB files | `var/tenants` |
| `UPLOADS_DIR` | Uploaded client files | `var/uploads` |
| `LLM_PROVIDER` | `mock` \| `openrouter` | `mock` |
| `OPENROUTER_API_KEY` | OpenRouter key | — |
| `OPENROUTER_MODEL` | Model slug; verify exact slug on openrouter.ai/models | Claude Haiku 4.5 slug |
| `OPENROUTER_ZDR` | Ask OpenRouter to use zero-data-retention providers only (verify request field names in current OpenRouter docs) | `true` |
| `LLM_MAX_USD_PER_RUN` | Hard spend cap for one job/script run | `1.00` |
| `CLASSIFIER_PROVIDER` | Provider for the existing daily classifier: `anthropic` (today) \| `openrouter` | `anthropic` |
| `JWT_SECRET` | Signing key for login cookies | random in dev |
| `SCHEDULER_ENABLED` | Run the daily pipeline inside the backend | `false` in dev |
| `PIPELINE_CRON_IST` | When the daily monitor runs | `06:17` |
| `NOTIFY_ENABLED` | Whether the pipeline sends email from this environment | `false` in dev |
| `DEADLINE_DATES` | Commencement phases for countdowns (single setting; the 13-vs-14 Nov question is open) | `2025-11-13,2026-11-13,2027-05-13` |
| `MAX_UPLOAD_MB` | Upload size limit | `25` |
| `BACKEND_URL` | Where the Next.js app forwards `/api/*` requests | `http://localhost:8000` |
| `REDACT_BEFORE_LLM` | Mask emails/phones/ID-like numbers before sending client text to an LLM | `true` |

## 5. Databases and data model

SQLite everywhere, accessed through SQLAlchemy 2.0. Every connection sets
`PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`.
Migrations: numbered `.sql` files per DB kind, applied in order by
`app/db/migrate.py`, recorded in a `schema_version` table. Migrations must be
idempotent and **must not alter existing library tables in a way the current
`src/` pipeline can't handle** (add tables/columns only).

### 5.1 Library DB (`library.db` = the existing `dpdpa.db` schema + new tables)

Existing (keep): `provisions`, `change_log`, `source_log`, `source_snapshot`.

New:

- `regulations(regulation_id TEXT PK, name, short_name, regulator, instrument_type, url, active INTEGER)`
  seeded: `DPDP-ACT-2023`, `DPDP-RULES-2025`. (RBI etc. later — nothing else may assume only DPDP.)
- `provision_regulation(provision_id PK → provisions, regulation_id → regulations)`
  (filled from the `DPDPA-`/`DPDPR-` prefix; avoids altering `provisions`).
- `library_versions(version INTEGER PK, published_at, published_by, note, change_ids TEXT, obligation_ids TEXT)`
  version 1 = initial baseline.
- `obligations(obligation_id TEXT PK 'OBL-0001', regulation_id, title, requirement_text,
  actor TEXT ('Data Fiduciary','Significant Data Fiduciary','Consent Manager','Data Processor', ...),
  applicability_tags TEXT (JSON list), commencement_date, severity ('High','Medium','Low'),
  penalty_ref TEXT (e.g. 'Schedule item 1'), max_penalty_inr_crore REAL, evidence_expected TEXT,
  keywords TEXT (JSON list), topic TEXT, status ('Draft','Published','Needs Review','Retired'),
  version_introduced INTEGER, version_retired INTEGER, created_by, reviewed_by, review_date,
  content_hash TEXT, notes)`
- `obligation_provisions(obligation_id, provision_id, excerpt TEXT, PRIMARY KEY(obligation_id, provision_id))`
  — `excerpt` must appear verbatim in `provisions.full_text` (enforced by a test).
- `library_audit(id INTEGER PK, at, actor, action, object_type, object_id, detail JSON)`

Obligations in library version *v* = rows with `status IN ('Published','Retired')`,
`version_introduced <= v` and (`version_retired IS NULL OR version_retired > v`).

### 5.2 Platform DB (`platform.db`)

- `users(user_id PK, email UNIQUE, name, password_hash, role, tenant_id NULL, active, created_at, last_login_at)`
  roles: `ey_admin`, `ey_consultant`, `client_viewer`, `client_contributor`.
  EY roles have `tenant_id NULL`; client roles must have one tenant.
- `consultant_assignments(user_id, tenant_id)` — which tenants an `ey_consultant` may see.
- `tenants(tenant_id PK, slug UNIQUE, name, deployment_model ('A','B','C'), status ('active','archived'), created_at, db_path, notes)`
- `jobs(job_id PK, kind, tenant_id NULL, payload JSON, status ('queued','running','done','failed'), created_at, started_at, finished_at, error, result JSON)`
- `llm_calls(id PK, at, purpose, tenant_id NULL, model, provider, input_tokens, output_tokens, cost_usd, prompt_hash, status, error)`
- `platform_audit(id PK, at, actor, action, object_type, object_id, detail JSON)`

### 5.3 Tenant DB (`tenants/<slug>.db`, one per client)

- `client_profile(key PK, value)` — name, sector, contact, etc.
- `applicability_answers(question_id PK, answer, answered_by, answered_at)`
- `kb_documents(doc_id PK, filename, mime, sha256 UNIQUE, size_bytes, uploaded_by, uploaded_at, status ('processing','ready','failed'), error, page_count, stored_path)`
- `kb_chunks(chunk_id PK, doc_id → kb_documents, seq, location TEXT ('p.3', 'Sheet1!A1:D20', 'slide 4', heading), text)`
  + `kb_chunks_fts` FTS5 virtual table over `text` (content table = kb_chunks).
- `assessments(obligation_id PK, status ('Compliant','Partial','Gap','Not applicable','Not assessed'),
  source ('ai','ey_verified'), confidence REAL, rationale, evidence JSON [{chunk_id, doc_id, location, quote}],
  missing_elements TEXT, library_version INTEGER, model, stale INTEGER (1 = needs re-assessment),
  assessed_at, reviewed_by, reviewed_at, review_comment)`
- `assessment_history(id PK, obligation_id, snapshot JSON, changed_at, changed_by)` — every change to an assessment row.
- `actions(action_id PK, obligation_id, title, owner, due_date, status ('open','in_progress','done'), created_at, updated_at, notes)`
- `alerts(alert_id PK, kind ('update_under_review','update_approved','reassessment'), change_id, obligation_id, created_at, seen_at)`
- `score_snapshots(snapshot_date PK, readiness_pct, high_gaps, coverage_pct, verified_pct, library_version)`
- `tenant_audit(id PK, at, actor, action, object_type, object_id, detail JSON)`

## 6. Approval model (the fix for "approvals keep coming back")

Principle: **alert immediately, score only after EY approval.**

- The daily monitor keeps applying detected text changes to `provisions`
  immediately (so the reference Word/Excel stay current and highlighted), BUT
  on `platform-build` `apply_change.py` records `regulatory` changes as
  `review_status='Pending Review'`, `reviewed_by=NULL`. `data_correction` rows are
  recorded `Approved` by `auto`.
- A pending regulatory change immediately creates an `update_under_review`
  alert for every tenant with an applicable obligation linked to that provision.
  **It does not change any client score.**
- EY Admin approves in the admin console (or API). Approving:
  1. sets `review_status='Approved'`, `reviewed_by`, `review_date`;
  2. flags obligations linked to the provision as `Needs Review` (EY edits the
     obligation wording if needed, then publishes);
  3. creates a new `library_versions` row when the approval is published
     (approvals and obligation publishes can be batched into one version);
  4. writes `library_audit`.
- Rejecting: sets `Rejected` and **reverses the text span** in `provisions`
  (replace `new_full_text` with `old_full_text` if it occurs exactly once;
  otherwise refuse and flag for manual fix — never guess).
- Tiering: `data_correction` → auto; `Clarification`/`Correction` with
  confidence ≥ 0.9 → one-click approve; `Amendment`/`Repeal`/`New Provision` or
  confidence < 0.9 → approval requires the approver to tick "I have checked the
  obligation wording" (UI) / `checked_obligations=true` (API).
- Interim (before the platform is live, production on `main`): approvals via
  `scripts/review.py` run by the **"Approve changes"** GitHub Action on GitHub's
  copy of the DB (Session 1). Excel is a read-only report.

## 7. Obligations checklist

- One obligation = one duty a regulated entity must perform, written in plain
  English, e.g. "Report a personal data breach to the Board within 72 hours of
  becoming aware of it, with the details in Rule 7(2)(b)."
- Drafted by LLM from each provision's verbatim text with a required verbatim
  `excerpt` anchor (checked in code), then reviewed by EY legal. Provisions that
  create no duty for regulated entities (e.g. Board constitution) get an explicit
  "no client obligation" note so coverage is provable.
- `severity` default from the Act's Schedule penalty linked to the duty
  (≥ ₹150 crore → High; ≥ ₹50 crore → Medium; otherwise Low) — verify each
  amount against the Schedule text in `provisions`; EY can override.
- `commencement_date` from the linked provisions' `effective_date` (if linked
  provisions differ, use the latest and note it).
- `applicability_tags` link to questionnaire answers (Section 8).
- Nothing is `Published` for real use without EY legal sign-off. In the dev DB,
  `--dev-publish` may publish drafts so later sessions have data to test with;
  such rows are labelled `notes: 'DEV-PUBLISHED, not EY-approved'`.

## 8. Applicability questionnaire

`backend/app/config_data/applicability.yaml` — ~15 yes/no questions, each with
an id, plain question text, help text, and the tag(s) it switches on/off.
Draft set: processes digital personal data in India (all); notified as a
Significant Data Fiduciary (`sdf`); processes children's data (`children`);
processes data of persons with disabilities via guardians (`disability`);
is a registered Consent Manager (`consent_manager`); relies on Consent
Managers (`uses_consent_manager`); transfers personal data outside India
(`cross_border`); uses Data Processors (`processors`); is a State
instrumentality (`state`); processes for research/archiving/statistics
(`research`); is a notified startup / class exempted under Section 17(3)
(`startup_exempt`); is an online gaming / social media / e-commerce
intermediary above the Third Schedule thresholds (`third_schedule_entity`);
processes employment data (`employment`); has a website/app offering notices
in multiple languages (`eighth_schedule_languages`). EY reviews this list.
Obligation applies to a tenant if its tags are all satisfied (`all` always true).

## 9. Client knowledge base ingestion

- Upload types: pdf, docx, xlsx, pptx, txt, md, csv, html. Size ≤ `MAX_UPLOAD_MB`.
  Reject others with a clear message. Deduplicate by sha256.
- Extraction: `pypdf` (fallback `pdfplumber`), `python-docx`, `openpyxl`,
  `python-pptx`, stdlib for text. **Extraction failure → document status
  `failed` with the real error shown to the user; never an empty "ready" doc.**
- Chunking: ~1,200 characters with ~150 overlap, split on paragraph/heading
  boundaries where possible; keep a human `location` (page, sheet/range, slide, heading).
- Search: SQLite FTS5 with bm25 ranking (no embeddings service needed).
- Redaction (`services/redaction.py`) before any client text is sent to an LLM:
  emails, Indian phone numbers, PAN-like and Aadhaar-like numbers → placeholders.
  Stored text stays original. Redaction has tests.
- Files stored under `UPLOADS_DIR/<slug>/`; tenant export = zip of tenant DB +
  uploads; tenant erase deletes both (this is itself the DPDP erasure duty).

## 10. Mapping engine

For each applicable obligation in the current library version:
1. Retrieve top 8 chunks with FTS5 using the obligation's keywords + title.
2. Ask the LLM (OpenRouter, strict JSON output, temperature 0) whether the
   evidence meets the obligation. Output schema:
   `{status: Compliant|Partial|Gap|Insufficient evidence, confidence: 0..1,
   rationale, missing_elements, evidence: [{chunk_id, quote}]}`.
3. **Verify every quote exists verbatim** (whitespace-normalised) in the cited
   chunk. Drop invalid quotes. If status is Compliant/Partial and no valid quote
   remains → store as `Not assessed` with rationale "AI evidence could not be verified".
   `Insufficient evidence` is stored as `Gap` only if confidence ≥ 0.7, else `Not assessed`.
4. Store in `assessments` with `source='ai'`, library version, model; write history.
5. Cache: skip if (obligation content_hash, chunk ids, model) unchanged.
6. Cost: log every call in `llm_calls`; stop the job cleanly when
   `LLM_MAX_USD_PER_RUN` would be exceeded, marking remaining items `Not assessed`
   and reporting it (never silently).
7. OpenRouter client must treat an HTTP 200 whose body contains `"error"` as a
   failure (the Sept 2026 lesson), retry up to 3 times with backoff, and surface
   the real error.
8. Consultant review: confirm or override (status + comment) → `source='ey_verified'`.
   An EY-verified row is never overwritten by AI; on law change it is marked `stale` instead.
9. Gap/Partial → auto-create a draft action if none exists.
Long-running work runs as a `jobs` row processed by a simple in-process worker
(no Redis/Celery — SQLite only).

## 11. Change propagation

- Regulatory change detected (pending) → alerts for affected tenants (Section 6).
- Change approved → linked obligations `Needs Review`.
- Obligation published/changed/retired (new library version) → for each tenant
  where it applies: assessment marked `stale=1` (or created as `Not assessed`),
  a `reassessment` alert added, and a mapping job queued for **only those
  obligations**.
- Dashboard shows "assessed against version X, current version Y" when stale.

## 12. KPIs (backend `services/kpis.py`, exact formulas)

Let A = applicable obligations for the tenant in the current library version,
excluding `Not applicable`.

| KPI | Formula |
|---|---|
| Readiness % | (Compliant + 0.5 × Partial) ÷ (assessed items in A, i.e. excluding `Not assessed`) × 100; also per topic and per commencement phase |
| Open gaps by severity | count of Gap + Partial by obligation severity |
| Deadline readiness | readiness % per phase in `DEADLINE_DATES`, with days remaining from today |
| Max penalty exposure | sum of distinct Schedule maximums (₹ crore) across Schedule items with ≥1 open Gap/Partial obligation — labelled "legal ceiling, not a prediction" |
| New regulatory updates | alerts since the tenant's last dashboard visit, split under review / approved |
| Assessment coverage | assessed ÷ A; and EY-verified ÷ assessed |
| Remediation progress | actions open / in progress / done / overdue |
| Evidence freshness | % of `ready` documents uploaded > 365 days ago |
| Readiness trend | weekly `score_snapshots` |

Every KPI has a unit test on the fictional client with hand-computed expected values.

## 13. Deployment and cutover (prepared in Session 8, executed only by Gautam)

- Docker: `backend` (uvicorn), `frontend` (next start), one volume for `var/`.
- Backups: nightly `sqlite3 .backup` of every DB to `var/backups/<date>/`, keep 14 days, restore tested.
- CI: `.github/workflows/ci.yml` runs backend pytest + frontend lint/build on pushes to `platform-build`.
- Cutover (after EY IT approves hosting): deploy → copy latest `db/dpdpa.db` from
  GitHub `main` to server `var/library.db` → run migrations → enable
  `SCHEDULER_ENABLED` → disable the GitHub daily cron (keep manual run) →
  stop tracking `db/`, `docs/*.docx`, `data/*.xlsx` in git → merge `platform-build`.

## 14. Security basics

- Passwords: argon2 or bcrypt. Login sets an httpOnly, Secure (prod), SameSite=Lax
  JWT cookie; 8-hour expiry. Login rate-limited.
- Every tenant route goes through `require_tenant_access(tenant_id)`:
  client users → only their tenant; `ey_consultant` → assigned tenants; `ey_admin` → all.
  Cross-tenant attempts return 404 and are audited. A test enumerates all tenant routes.
- The frontend proxies `/api/*` to the backend (Next.js rewrites) — no open CORS.
- Every screen shows the disclaimer: "AI-assisted assessment. Items marked
  EY-verified have been reviewed by EY. Not legal advice."

## 15. Session plan

| Session | Delivers | Gate before next |
|---|---|---|
| 1 | Interim approval fix on `main` (review script, Approve-changes Action, read-only Excel) + `platform-build` branch + backend skeleton, config, migration runner, dev bootstrap | Tests green; Gautam OKs push of part A |
| 2 | Platform DB, auth & roles, OpenRouter/mock LLM layer, approval services & admin API, pipeline runner & scheduler, pipeline → Pending Review | Approve/reject via API works on dev DB |
| 3 | Obligations: tables, drafting script (LLM, verbatim excerpt check), severity/commencement, questionnaire YAML, admin API, coverage report | Draft checklist ready for EY legal |
| 4 | Tenants, tenant DBs, isolation, questionnaire answers, document upload/extraction/chunking/FTS, redaction, fictional client fixtures | Upload → searchable chunks works |
| 5 | Mapping engine, quote verification, jobs worker, consultant review API, actions, change propagation, accuracy check on fictional client | Accuracy measured and reported |
| 6 | Next.js app: login, layout, EY admin console (approvals, versions, obligations, tenants, mapping review) | `npm run build` + lint green |
| 7 | KPI service + API, client dashboard pages, drill-down, uploads page, actions, board-pack export | KPI tests green; dashboard renders fictional client |
| 8 | Hardening, Docker, backups, CI, end-to-end rehearsal with simulated law change, RUNBOOK, cutover checklist, PR description | Ready for Gautam's decisions |
