# Session 6 — Next.js app foundation + EY admin console

Branch: `platform-build`. Read first: `CLAUDE.md`, `platform/SPEC.md` (§2, §6, §14),
`platform/CHECKPOINT.md`, `platform/prompts/_SESSION_RULES.md`. Skim the backend
routers (`backend/app/api/`) — the frontend must use the API exactly as built.
AI spend allowed: **$0**.

## Goal (plain words)
Build the web screens EY staff use: log in, see and approve law changes (with a
clear before/after view of the wording), manage the obligations checklist,
create client spaces, and review the AI's findings for each client.

## Tasks

**6.1 Setup**: `node -v` (need ≥ 20) and `npm -v`. If missing/blocked, mark 6.x
`[!]`, write install steps for Gautam (Node LTS installer from nodejs.org; if
Device Guard blocks it, EY IT must allow it) and stop the session cleanly.
Scaffold `frontend/` with `create-next-app` (App Router, TypeScript, Tailwind,
ESLint, `src/` dir), add Recharts. `next.config` rewrite `/api/:path*` →
`BACKEND_URL` (default `http://localhost:8000`). A typed API client
(`src/lib/api.ts`) with error handling that shows the backend's real error
message (no silent failures). Document `npm run dev` + backend start in
`frontend/README.md`.

**6.2 Auth & layout**: login page; session via the backend cookie (`/api/auth/me`
on load); redirect by role (EY → `/admin`, client → `/client`); top bar with user,
role and (for clients) tenant name; role-based nav; logout; the disclaimer from
SPEC §14 in the footer on every page. Accessible (labels, focus states, keyboard).

**6.3 Approvals queue** `/admin/changes`: tabs Pending / Approved / Rejected;
columns reference, type, origin, detected date, source, confidence; filters;
checkbox bulk approve/reject with a required note; detail page with old vs new
text as a word-level diff (use the diff from the API), source link, linked
obligations; the "I have checked the obligation wording" tickbox appears when
SPEC §6 tiering requires it; approve/reject buttons show the API's result or error.

**6.4 Library** `/admin/library`: versions list (what each version changed);
"Publish new version" (select approved changes + obligations, note).
`/admin/obligations`: table with status/topic/severity/actor filters and search;
detail/edit form (wording, tags from the questionnaire list, severity,
evidence expected, keywords) showing linked provision excerpts; status changes;
a clear banner on publish: "Publishing makes this obligation count in client
scores. EY legal sign-off required."

**6.5 Tenants & review**: `/admin/tenants` list/create (slug, name, deployment
model), assign consultants, export, archive, erase (type the slug to confirm).
`/admin/tenants/[id]/review`: obligations with AI status, confidence, evidence
quote + document location, stale flag; confirm/override with comment; filter
"needs review" (AI-only, low confidence, stale); "Run mapping" button with job
progress polling.

**6.6 Quality**: `npm run lint` and `npm run build` must pass. Manually run
backend + frontend against the dev data (fictional client) and walk through each
page; record what you checked in the session log. If Playwright works on this
machine, add 2–3 smoke tests; if not, note it and skip.

**6.7 Wrap up** per the rules file. CHANGELOG: how to start the app locally
(exact commands), which pages exist, a screenshot description of the approval flow.

## Done when
An EY admin can log in, approve/reject a pending change, publish a version, edit
an obligation, create a tenant and review mapping results — all in the browser;
lint/build green; branch pushed.
