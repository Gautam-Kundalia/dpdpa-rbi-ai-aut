# Session 7 — KPIs and the client dashboard

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§12, §14),
`platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`, and the frontend
structure built in Session 6. AI spend allowed: **$0**.

## Goal (plain words)
Give each client a dashboard that a CXO understands in five seconds — how ready
they are, how many serious gaps they have, and how many days until the next
deadline — with detail one click below, plus a downloadable "board pack".

## Tasks

**7.1 KPI service + API** (`app/services/kpis.py`, `app/api/tenant_dashboard.py`):
implement every KPI in SPEC §12 with the exact formulas; `DEADLINE_DATES` from
config (one setting — the 13 vs 14 Nov question is open). Endpoints under
`/api/tenants/{tenant_id}/dashboard/`: `summary` (3 headline numbers + library
version + stale count), `topics` (topic × status matrix), `deadlines`,
`exposure` (Schedule items with open gaps, each with ₹ crore ceiling and the
obligations behind it), `updates` (alerts; `POST .../updates/seen`), `coverage`,
`actions`, `freshness`, `trend`. Weekly `score_snapshots` job (and on each
completed mapping run). **Unit tests on the fictional client with hand-computed
expected values for every KPI**, including edge cases: no assessments yet, all
N/A, zero actions.

**7.2 Client dashboard** `/client` (and the same view for EY at
`/admin/tenants/[id]/dashboard`):
- Row 1 — three headline tiles: Readiness % (with "based on X of Y obligations
  assessed; Z% EY-verified"), Open high-severity gaps, Days to next deadline (date shown).
- Alert strip: regulatory updates (under review vs approved) and "N items being
  re-assessed after a law change".
- Topic × status heatmap; deadline readiness by phase; penalty exposure list
  labelled "legal maximum under the Act's Schedule — not a prediction";
  coverage (AI-suggested vs EY-verified); remediation (open/in progress/done/overdue);
  evidence freshness; readiness trend line.
- Charts: Recharts, colour-blind-safe palette, status colours consistent
  everywhere (Compliant/Partial/Gap/Not assessed/N/A), text labels not colour
  alone, readable on mobile width, empty states that say what to do next.

**7.3 Detail pages**: `/client/obligations` (filterable list) and
`/client/obligations/[id]` (plain requirement, the law's verbatim excerpt,
status, evidence quote with document + location, AI vs EY-verified badge,
library version, related actions); `/client/documents` (upload with progress,
status, failed-with-reason, delete for contributors); `/client/actions` (list,
edit owner/due/status for contributors).

**7.4 Board pack**: `GET /api/tenants/{tenant_id}/exports/board-pack.xlsx`
(summary, gaps by severity, deadlines, actions, disclaimer; generated with
openpyxl) and a print-friendly `/client/report` page (browser "Save as PDF").
Tests for the workbook content.

**7.5 Quality**: backend tests, `npm run lint`, `npm run build` green. Walk
through the fictional client's dashboard as a `client_viewer` user and as EY;
confirm a client user cannot reach any other tenant's pages (UI + API). Record
in the session log.

**7.6 Wrap up** per the rules file. CHANGELOG: describe each KPI in one plain
sentence and how to see the fictional client's dashboard.

## Done when
The fictional client's dashboard shows every KPI with correct numbers (tests
prove the maths), drill-downs and exports work, lint/build/tests green, branch pushed.
