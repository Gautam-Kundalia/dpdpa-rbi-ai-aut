# DPDPA / RBI Regulatory Change Tracker

Automation project to keep consultants current on DPDP Act, 2023 / DPDP
Rules, 2025 (and later, RBI) updates without manual monitoring.

**Current scope:** DPDP Act + Rules baseline loaded (all 48 Act rows and
31 Rules rows verbatim from the official PDFs), and the daily
fetch/classify/apply/notify pipeline is built and running. RBI comes
later once this half is proven out in production.

## Architecture

```
PIB (RSS, English) -----\
MeitY (working copy) -----+--> src/fetch_sources.py --> source_log (hash-based
eGazette (weak signal) --/                                change detection)
                                                              |
                                                    changed sources only
                                                              v
                                                src/classify_change.py
                                       (diff-first: only the changed
                                        passages go to the model —
                                        Claude Haiku 4.5, forced tool-use,
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
text** (`provisions.full_text` — word for word from the official Act and
Rules PDFs, no paraphrasing, no abridging). The Excel workbook and the two
Word documents are both *generated from* SQLite — don't hand-edit them
expecting it to persist; re-running the export scripts will overwrite them.

## Every change is recorded, but only a REAL one is ever highlighted

Every row `apply_change.py` and the one-off correction scripts write goes
into `change_log`, permanently, as an audit trail. But `change_log.change_origin`
tells two very different kinds of row apart:

- **`regulatory`** — the government actually changed the law or rules: an
  amendment, a repeal, a clarification, or an official corrigendum. **Only
  these are ever highlighted.**
- **`data_correction`** — *we* fixed our own data: a typo, a paraphrase
  replaced with verbatim text, text that was missing at seeding. The law
  itself didn't change. These are never highlighted anywhere — they exist
  in `change_log` purely as a record of what was fixed and why.
- **`baseline`** — the initial seed load. Not a change at all.

Within a `regulatory` change, only the **words that actually changed** are
highlighted — not the whole provision. `export_word.py` compares the
change's `old_full_text`/`new_full_text` word by word (`src/word_diff.py`,
shared with the notification email so the two always agree): inserted or
replaced words get a yellow highlight, removed words get a grey
strikethrough shown inline immediately before the text that replaced them,
and a small caption names the source document and change ID. If a
provision's text has since changed again (a later data correction, say)
so the recorded change no longer matches verbatim, the text renders
plainly with the caption and a warning is logged — it never silently
mis-highlights. The Excel tracker mirrors this: `Change_Log` fills an
entire row light yellow only for a `regulatory` row, and
`Master_Provisions` gets a computed `Last_Regulatory_Change` cell
(highlighted, never the whole row).

## Sources & change detection

Three sources, in trust order:

1. **PIB** — an RSS feed (`RssMain.aspx?...&lang=1`), explicitly
   parameterised to English. This replaced scraping PIB's HTML "all
   releases" page, which could silently serve Hindi depending on the
   requesting client's apparent locale with no way to confirm what
   language GitHub Actions' server would see.
2. **MeitY** — the two known static PDF paths (DPDP Rules 2025, DPDP Act
   2023) — the most reliable source, direct file URLs. (MeitY does have a
   page listing DPDP documents, which would catch a *new* notification or
   corrigendum that these two fixed PDF URLs can't — but it's a Next.js
   single-page app with no server-rendered content and no reachable JSON
   API; a plain GET returns an empty shell. Investigated, not wired up —
   see `fetch_sources.py`'s header comment.)
3. **eGazette** (`https://egazette.gov.in/`) — meant to be the
   authoritative confirmation source, but its real notification search is
   a session-scoped ASP.NET postback form (no stable endpoint found).
   Currently hashes the home page as a coarse best-effort signal — **known
   limitation**. Also required disabling TLS verification specifically for
   this host (its cert chains to a root Windows trusts but the `certifi`
   bundle doesn't — verified by hand via a raw TLS socket check, not
   blanket-disabled).

`fetch_sources.py` hashes *extracted, cleaned text* (not raw bytes) so PDF
metadata churn and HTML analytics-script noise don't cause false-positive
"changes." Each source has exactly one row in `source_log` (its `url`
column is `UNIQUE`) that gets updated on every fetch, not a new row per
run — so `source_log` shows what's being watched right now, not a history
of past runs. A download failure keeps the last known-good fingerprint
(doesn't blank it) and is surfaced into the run's error list and exit
code, rather than being silently swallowed.

## Classification: diff-first, not "send the whole document"

`classify_change.py` doesn't send the model the whole fetched document —
it keeps a snapshot of the text from the last *successfully classified*
fetch of each source (`source_snapshot` table) and diffs the new fetch
against it in plain Python (`difflib`) first. Only the changed passages —
capped at ~20,000 characters, plus only the provisions whose section/rule
number appears in the diff — go to the model.

- **First time a source is seen** (no snapshot yet): one is stored and the
  run reports "baseline captured" — a normal outcome, not an error, and it
  makes no AI call.
- **Mostly-Hindi changed lines are dropped** before sending (English is
  authoritative for this tracker), line by line rather than whole-diff-hunk,
  so a real English change sitting next to unrelated Hindi context isn't
  thrown out along with it.
- **PIB**: since a changed passage is just release titles, only a title
  matching a DPDP-relevant keyword is sent at all — no match means "No
  Change Detected" with no AI call.
- The model is told explicitly that it's reading a diff of the official
  source against itself over time — never a comparison of our stored text
  against the source, which isn't its job. `old_full_text`/`new_full_text`
  are validated (normalized substring match) against the provision's
  actual current text and the actual fetched content before anything is
  trusted.
- `apply_change.py` replaces only the matched span inside a provision's
  `full_text` — never the whole provision — and refuses (writes nothing)
  unless that span appears in the current text exactly once.

## Classification & auto-apply — no human review gate

This is a **deliberate project decision**: detected changes are classified
by Claude (`CLAUDE_MODEL` in `.env`, defaulting to `claude-haiku-4-5`, via
the Anthropic API with forced tool-use) and applied straight to
`provisions` immediately, with no pending-review step. `Review_Status` on
a `change_log` row records how confident the automated classification
was — it is **not** a queue waiting for a consultant's sign-off. If a
human check before a change goes live is wanted, that would need to be a
deliberate change to the pipeline; right now, it isn't there.
`classify_change.py`'s prompt is built to return an empty change list
rather than guess when it can't find confident verbatim text, and both
`classify_change.py` and `apply_change.py` fail safe (mark
`source_log.processing_status = 'Error'`, roll back the source's
fingerprint so the next run retries, and skip auto-apply) on any parse/
validation failure rather than writing malformed data.

A provision's plain-language `current_summary` is never overwritten by
the pipeline, even when its `full_text` changes — that could silently
replace a good human-written summary with a worse auto-generated one. The
notification email points at `Change_Log`'s before/after summary for what
actually changed, and flags that the provision's own summary may need a
human update.

## Project layout

```
db/
  schema.sql        table definitions (provisions, change_log, source_log,
                     source_snapshot)
  dpdpa.db          the actual database — source of truth, committed to git
  backup/           pre-fix database snapshots (gitignored)
docs/
  DPDP_Rules_2025.docx           generated consolidated Rules document
  DPDP_Act_2023.docx             generated consolidated Act document
  act_verbatim_rebuild_2026-09-23.md   row-by-row report from the Act
                                  verbatim rebuild (similarity scores,
                                  which checks passed, word-level diffs)
data/
  act_verbatim_2026-09-23.json    the checked, code-extracted Act text
  DPDP_Rules_Tracker.xlsx         generated Excel view — committed to git
scripts/
  rebuild_act_verbatim_2026-09-23.py     one-time: rebuilt all 48 Act rows
                                          verbatim from the official PDF
  apply_rules_corrigendum_2026-09-23.py  one-time: applied G.S.R. 892(E)
  apply_summary_fixes_2026-09-23.py      one-time: 5 pre-approved summary fixes
src/
  db.py                     connection + schema init helper (idempotent migrations)
  init_db.py                creates db/dpdpa.db from schema.sql (empty)
  seed_dpdp_rules_full.py   loads all 23 Rules + 7 Schedules (verbatim)
  seed_dpdp_act_full.py     loads all 44 Act sections + Schedule, from
                             data/act_verbatim_2026-09-23.json
  fetch_sources.py          fetches PIB/MeitY/eGazette, hash-based change detection
  classify_change.py        diff-first classification -> Claude Haiku 4.5,
                             strict tool-use, validated
  apply_change.py           applies a validated change to provisions + change_log
  word_diff.py              word-level diff shared by export_word.py and notify.py
  notify.py                 one Gmail SMTP summary email per run
  run_pipeline.py           daily entrypoint: wires all of the above together
  export_word.py            SQLite -> the two consolidated .docx files
  export_excel.py           SQLite -> the Excel tracker
tests/
  conftest.py, test_*.py    pytest suite — every test uses a throwaway
                             SQLite file, never db/dpdpa.db
.github/workflows/
  daily-check.yml           daily cron (06:17 IST), runs run_pipeline.py,
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
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-haiku-4-5
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...     # 16-char Gmail app password, not your account password
NOTIFY_EMAIL=...
```

For the GitHub Actions cron to run, add the same as repo secrets under
**Settings → Secrets and variables → Actions**: `ANTHROPIC_API_KEY`,
`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL` (`CLAUDE_MODEL` can
be a repo *variable* instead of a secret — it has a matching default
baked into the workflow, so it's optional either way).

## Usage

```bash
python src\init_db.py                    # empty schema (only if db/dpdpa.db doesn't exist yet)
python src\seed_dpdp_rules_full.py       # load the 31 Rules provisions
python src\seed_dpdp_act_full.py         # load the 48 Act provisions
python src\export_word.py                # generate the two Word docs
python src\export_excel.py               # generate the Excel tracker

python src\run_pipeline.py               # the daily pipeline, run manually

pytest tests/                            # run the test suite (scratch DBs only)
```

The GitHub Actions workflow runs `run_pipeline.py` automatically every day
at 06:17 IST (cron is UTC-specified; see the workflow file — GitHub may
still start it hours late, a scheduler-queueing effect outside this
pipeline's control), and can also be triggered manually from the Actions
tab (`workflow_dispatch`).

## Not yet built

- A stable, verified eGazette search/filter endpoint (currently best-effort
  home-page hashing — see "Sources & change detection" above)
- A reachable endpoint for MeitY's own DPDP-documents listing page (it
  exists but is a client-side-rendered SPA — see above)
- RBI half of the project

## Known limitations

- **eGazette** doesn't have a confirmed stable search endpoint yet (see
  above) — its signal is weaker than PIB/MeitY.
- **No human review gate** on auto-applied changes — by design, not an
  oversight; see "Classification & auto-apply" above.
- New amendments/corrigenda are only caught if they change one of the two
  fixed MeitY PDF URLs this pipeline watches, or if PIB publishes a
  DPDP-relevant press release the same day it's checked. A notification
  published only as a brand-new Gazette PDF, with no matching PIB release,
  would not currently be detected automatically.
