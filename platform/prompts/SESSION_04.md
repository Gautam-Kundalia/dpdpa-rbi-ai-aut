# Session 4 — Client spaces (tenants) and knowledge-base ingestion

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§5.2, §5.3,
§8, §9, §14), `platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`.
AI spend allowed: **$0** (no LLM calls in this session).

## Goal (plain words)
Each client gets its own private, separate database file and upload folder.
Clients answer the applicability questions, upload their policies and
procedures, and the system turns those files into searchable passages — with
personal details masked before anything could ever go to an AI.

## Tasks

**4.1 Tenant DB + service**: `migrations/tenant/001_*.sql` (SPEC §5.3 incl. the
FTS5 table and triggers keeping it in sync), models, `app/services/tenants.py`:
`create(slug, name, deployment_model)` → platform row + new DB file under
`TENANTS_DIR` + upload folder; `list`, `archive`, `export(slug) -> zip path`
(DB + uploads + a manifest), `erase(slug, confirm_slug)` (deletes DB + uploads,
keeps an audit row with no client content). Admin API `app/api/admin_tenants.py`
(create/list/archive/export/erase; erase needs `ey_admin` and the slug typed
again). Check FTS5 is available in the local SQLite build; if not, record a
blocker with the exact error. Tests.

**4.2 Isolation**: finish `require_tenant_access` (client users → own tenant only;
`ey_consultant` → assigned tenants via `consultant_assignments`; `ey_admin` → all;
denied → 404 + audit). Admin endpoint to assign consultants. Write
`backend/tests/test_tenant_isolation.py` that **enumerates every route whose path
contains `{tenant_id}`** and asserts a client user of tenant A gets 404 on
tenant B — so future routes are covered automatically.

**4.3 Questionnaire API** (`app/api/tenant_profile.py`): `GET
/api/tenants/{tenant_id}/questionnaire` (questions + current answers),
`PUT .../questionnaire` (answers; contributor or EY), `GET
.../applicable-obligations` (current library version, using Session 3 helpers).
Also profile key/values. Tests.

**4.4 Upload & extraction** (`app/services/ingestion.py`, `app/api/tenant_documents.py`):
`POST /api/tenants/{tenant_id}/documents` (multipart; size and type checks per
SPEC §9; sha256 dedupe → return the existing doc), `GET` list with status,
`GET /{doc_id}` (metadata + chunk count), `DELETE /{doc_id}` (removes chunks and
file). Extraction per format; **failure → status `failed` with the real error
text; never an empty "ready" document**. Processing can be synchronous for now
(Session 5 adds the jobs worker; structure the code so it can move there).
Tests for every format using generated fixtures, including a corrupt PDF.

**4.5 Chunking + search** (`app/services/retrieval.py`): chunk per SPEC §9 with
human-readable `location`; FTS5 index; `search(tenant, query, k=8)` with bm25,
safe against FTS5 syntax errors in user/obligation text (escape/quote terms).
Tests: relevant passage ranks first for a few known queries.

**4.6 Redaction** (`app/services/redaction.py`): emails, Indian mobile/landline
formats, PAN-like `[A-Z]{5}[0-9]{4}[A-Z]`, Aadhaar-like 12 digits (with/without
spaces) → `[EMAIL]`, `[PHONE]`, `[PAN]`, `[ID-NUMBER]`. Returns text + counts.
Tests including false-positive checks (e.g. section numbers, dates, ₹ amounts must not be masked).

**4.7 Fictional test client** `backend/tests/fixtures/acme_fictional/`:
"Acme Retail Pvt Ltd (FICTIONAL — test data only)". Generate 5–6 short
documents via a script (privacy notice, breach response SOP, data retention
schedule, consent & withdrawal procedure, vendor/processor agreement clause,
children's data statement), mixing docx/pdf/xlsx. Build in **deliberate,
documented gaps** (e.g. breach SOP says "notify the Board within 7 days" instead
of 72 hours; no children's verifiable-consent process; retention schedule
missing the 1-year log retention). Write `expected_labels.yaml`: for ~20 real
obligations from the dev library, the correct status and the sentence that
proves it. Include one fake email/phone to test redaction.

**4.8 Wrap up** per the rules file. CHANGELOG: explain tenants, isolation (why
one client can never see another's data), what file types work, what redaction masks.

## Done when
Create tenant → answer questionnaire → upload the fictional documents → search
returns the right passages; isolation test passes for every tenant route; all
tests green; branch pushed.
