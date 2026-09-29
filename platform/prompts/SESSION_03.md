# Session 3 — Obligations checklist

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§5.1, §6, §7,
§8, §11), `platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`.
AI spend allowed this session: **$2.00** (task 3.4 only). Use `LLM_PROVIDER=openrouter`
for that run if `OPENROUTER_API_KEY` is set; if not, stop at 3.3, mark 3.4 `[!]`
and tell Gautam exactly how to add the key to `.env`.

## Goal (plain words)
Turn the 79 legal provisions into a checklist of specific duties ("obligations")
that a client can be checked against. The AI writes a first draft; every draft
must point to the exact words in the law it came from (checked by code), and EY
legal reviews it before anything is used for real.

## Tasks

**3.1 Obligation services + admin API** (`app/services/obligations.py`,
`app/api/admin_obligations.py`):
`GET /api/admin/obligations?status=&topic=&regulation=`, `GET /api/admin/obligations/{id}`
(with linked provisions and excerpts), `PATCH /api/admin/obligations/{id}` (edit
wording, tags, severity, evidence_expected, keywords; recompute `content_hash`;
audit), `POST /api/admin/obligations/{id}/status` (Draft ↔ Needs Review; Retire),
publishing goes through `POST /api/admin/library/publish` (Session 2) which sets
`status='Published'`, `version_introduced`, and for retirements `version_retired`.
Helper `obligations_in_version(v)` per SPEC §5.1. Tests.

**3.2 Applicability questionnaire**: write `backend/app/config_data/applicability.yaml`
from SPEC §8 (id, question, help, tags_on_yes, tags_on_no). Loader + validation
(unique ids, known tags). `evaluate(answers) -> set(tags)` and
`obligation_applies(obligation, tags) -> bool`. Tests. Mark the file header
"DRAFT — to be reviewed by EY".

**3.3 Drafting script** `scripts/platform/draft_obligations.py`:
- Input: library DB (`DPDP_DB_PATH`), provider from `LLM_PROVIDER`, `--dry-run`,
  `--only DPDPR-R7,...`, `--max-usd`.
- For each provision (skip `Repealed`), send its verbatim `full_text`, reference
  and topic; ask for a JSON list of obligations: `title`, `requirement_text`
  (one duty, plain English), `actor`, `applicability_tags` (from the YAML tag
  list only), `excerpt` (exact words copied from the provision), `evidence_expected`,
  `keywords` (5–10 search words a client document would contain), or
  `{"no_client_obligation": "<reason>"}`.
- **Verify every `excerpt` appears verbatim** (whitespace-normalised) in that
  provision; reject and retry once with the error; still failing → record the
  provision in the coverage report as "needs manual drafting". Never store an unverified excerpt.
- `commencement_date` from provision `effective_date` (latest if several).
- Severity from the Act's Schedule (read Schedule text from `provisions`; map each
  obligation to a Schedule item where it clearly fits; ≥ ₹150 cr High, ≥ ₹50 cr
  Medium, else Low; unknown → Medium with note "severity to be set by EY").
  Keep the mapping of Schedule items → amounts in one table in code with the
  verbatim source line in a comment.
- De-duplicate near-identical obligations across Act and Rules (same duty:
  keep one, link both provisions).
- Writes `status='Draft'`, `created_by='ai-draft'`. Idempotent (re-run updates
  drafts, never touches rows EY edited — detect via `reviewed_by`/audit).
- Test fully with the mock provider on 3 real provisions from a temp DB copy.

**3.4 Real drafting run** on `var/library.db` within $2.00. Record: number of
obligations, provisions with no client obligation, provisions needing manual
drafting, cost. Then `--dev-publish` them into `var/library.db` only (SPEC §7
labelling) so later sessions have data. Never touch `db/dpdpa.db`.

**3.5 Review outputs for EY legal**:
- `docs/platform/obligation_coverage.md` — every provision → its obligations or
  the "no client obligation" reason; counts by topic/severity/actor; list of gaps.
- `scripts/platform/export_obligations_review.py` → a **read-only** review
  workbook (`var/exports/obligations_review_<date>.xlsx`, not committed) with a
  banner that edits are not saved and feedback goes to Gautam, who applies it via
  the admin console/API. Tests for both generators.

**3.6 Propagation part 1**: in `approvals.approve`, obligations linked to the
approved change's provision move to `Needs Review` (Published ones stay usable
until republished); audit row. Tests.

**3.7 Wrap up** per the rules file. CHANGELOG: explain what an obligation is,
how many were drafted, what EY legal must now review (decision D4), cost.

## Done when
Dev library has a full draft checklist with verified excerpts, coverage report
committed, review workbook generator works, all tests green, branch pushed.
