# DPDPA / RBI Regulatory Change Tracker

Automation project to keep consultants current on DPDP Act, 2023 / DPDP
Rules, 2025 (and later, RBI) updates without manual monitoring.

**Current scope:** DPDP Act + Rules baseline loaded, and the daily
fetch/classify/apply/notify pipeline is built and running. RBI comes
later once this half is proven out in production.

## Architecture

```
PIB (early warning) ---\
MeitY (working copy) ----+--> src/fetch_sources.py --> source_log (hash-based
eGazette (confirmation) -/                              change detection)
                                                              |
                                                    changed sources only
                                                              v
                                                   src/classify_change.py
                                                   (OpenRouter, strict JSON,
                                                    verbatim-text-or-nothing)
                                                              |
                                                     validated changes
                                                              v
                                                    src/apply_change.py
                                                    (auto-applied, no human
                                                     review gate)
                                                              |
                                                              v
                                                    db/dpdpa.db  (SQLite —
                                                    source of truth; full
                                                    verbatim clause text)
                                                              |
                        +-------------------------------------+
                        |                                     |
                        v                                     v
            src/export_word.py                    src/export_excel.py
            --> docs/DPDP_Rules_2025.docx          --> data/DPDP_Rules_Tracker.xlsx
            --> docs/DPDP_Act_2023.docx                (Master_Provisions/Change_Log/
                (legal-style layout,                     Source_Log — links jump
                 bookmarked, amendment                    straight into the docx)
                 highlighting)

src/run_pipeline.py orchestrates all of the above; src/notify.py sends one
summary email per run (Gmail SMTP) regardless of whether anything changed.
.github/workflows/daily-check.yml runs the whole chain on a daily cron and
commits db/docs/data back to the repo.
```

SQLite holds the real, current state, **including the verbatim clause
text** (`provisions.full_text` — no paraphrasing, no abridging). The Excel
workbook and the two Word documents are both *generated from* SQLite —
don't hand-edit them expecting it to persist; re-running the export
scripts will overwrite them.

**Amendment convention:** when the pipeline detects and applies a real
change, `export_word.py` renders it into the docx with the new text
highlighted yellow and the superseded text struck through directly below,
under a "Previous text (superseded)" label. This is dormant on the initial
baseline load (everything is `change_type = 'New Provision'`) but is fully
wired up and exercises on real detected changes.

## Sources & change detection

Three sources, in trust order:

1. **PIB** (`https://www.pib.gov.in/allRel.aspx`) — early-warning trigger.
   PIB's per-ministry filter is an ASP.NET postback with no stable
   GET/query-string form, so the whole "all releases" listing is hashed;
   any new press release (relevant or not) gets handed to the classifier.
2. **MeitY** — the two known static PDF paths (DPDP Rules 2025, DPDP Act
   2023) — the most reliable source, direct file URLs.
3. **eGazette** (`https://egazette.gov.in/`) — meant to be the
   authoritative confirmation source, but its real notification search is
   a session-scoped ASP.NET postback form (no stable endpoint found).
   Currently hashes the home page as a coarse best-effort signal — **known
   limitation**, flagged for follow-up. Also required disabling TLS
   verification specifically for this host (its cert chains to a root
   Windows trusts but the `certifi` bundle doesn't — verified by hand via
   a raw TLS socket check, not blanket-disabled).

`fetch_sources.py` hashes *extracted, cleaned text* (not raw bytes) so PDF
metadata churn and HTML analytics-script noise don't cause false-positive
"changes." Each source has exactly one row in `source_log` (its `url`
column is `UNIQUE`) that gets updated on every fetch, not a new row per
run.

## Classification & auto-apply — no human review gate

This is a **deliberate project decision**: detected changes are classified
by an LLM (via OpenRouter) and applied straight to `provisions`
immediately, with no pending-review step. `classify_change.py`'s prompt is
built to return an empty change list rather than guess when it can't find
confident verbatim text, and both `classify_change.py` and
`apply_change.py` fail safe (mark `source_log.processing_status = 'Error'`
and skip auto-apply) on any parse/validation failure rather than writing
malformed data.

Model: `OPENROUTER_MODEL` in `.env` currently points at a **free**
OpenRouter model (`nvidia/nemotron-3-ultra-550b-a55b:free` — 0 cost, 50
req/day at a $0 balance, well within this pipeline's ~4 calls/day).
Upgrading to a paid model later is a one-line env var change — the code
and prompt are model-agnostic.

## Project layout

```
db/
  schema.sql    table definitions (provisions, change_log, source_log)
  dpdpa.db      the actual database — source of truth, committed to git
docs/
  DPDP_Rules_2025.docx   generated consolidated Rules document
  DPDP_Act_2023.docx     generated consolidated Act document
  full_text/     OBSOLETE — leftover from an earlier design (small .md
                 files per provision). Safe to delete; full text now
                 lives in the database and is rendered into the two
                 docx files above instead.
data/
  DPDP_Rules_Tracker.xlsx   generated Excel view — committed to git
src/
  db.py                     connection + schema init helper
  init_db.py                creates db/dpdpa.db from schema.sql (empty)
  seed_dpdp_rules_full.py   loads all 23 Rules + 7 Schedules (verbatim)
  seed_dpdp_act_full.py     loads all 44 Act sections + penalty Schedule
  fetch_sources.py          fetches PIB/MeitY/eGazette, hash-based change detection
  classify_change.py        OpenRouter classification -> strict JSON, validated
  apply_change.py           applies a validated change to provisions + change_log
  notify.py                 one Gmail SMTP summary email per run
  run_pipeline.py           daily entrypoint: wires all of the above together
  export_word.py            SQLite -> the two consolidated .docx files
  export_excel.py           SQLite -> the Excel tracker
.github/workflows/
  daily-check.yml           daily cron (06:00 IST), runs run_pipeline.py,
                             commits db/docs/data back to the repo
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt   # use python -m pip if pip.exe is Device-Guard-blocked
```

Fill in `.env` (never committed — see `.gitignore`):

```
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...     # 16-char Gmail app password, not your account password
NOTIFY_EMAIL=...
```

For the GitHub Actions cron to run, add the same as repo secrets under
**Settings → Secrets and variables → Actions**: `OPENROUTER_API_KEY`,
`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL`
(`OPENROUTER_MODEL` has a matching free-model default baked into the
workflow, so it's optional there).

## Usage

```bash
python src\init_db.py                    # empty schema (only if db/dpdpa.db doesn't exist yet)
python src\seed_dpdp_rules_full.py       # load the 31 Rules provisions
python src\seed_dpdp_act_full.py         # load the 47 Act provisions
python src\export_word.py                # generate the two Word docs
python src\export_excel.py               # generate the Excel tracker

python src\run_pipeline.py               # the daily pipeline, run manually
```

The GitHub Actions workflow runs `run_pipeline.py` automatically every day
at 06:00 IST (cron is UTC-specified; see the workflow file), and can also
be triggered manually from the Actions tab (`workflow_dispatch`).

## Not yet built

- A stable, verified eGazette search/filter endpoint (currently best-effort
  home-page hashing — see "Sources & change detection" above)
- RBI half of the project

## Known limitations

- **eGazette** doesn't have a confirmed stable search endpoint yet (see
  above) — its signal is weaker than PIB/MeitY.
- **No human review gate** on auto-applied changes — by design, not an
  oversight; see "Classification & auto-apply" above.
- Classification currently runs on a free-tier LLM (see above) — cheaper
  but somewhat less capable than a paid frontier model; the prompt is
  designed to fail safe (return nothing) rather than guess.
