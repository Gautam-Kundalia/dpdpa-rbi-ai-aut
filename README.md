# DPDPA / RBI Regulatory Change Tracker

Automation project to keep consultants current on DPDP Act, 2023 / DPDP
Rules, 2025 (and later, RBI) updates without manual monitoring.

**Current scope:** DPDP Act + Rules baseline loaded. RBI comes later once
this half is working. Real-time fetching from MeitY/eGazette/PIB is not
yet built — everything currently in the database was loaded via one-time
seed scripts from verified Gazette text.

## Architecture (current)

```
Source (MeitY / eGazette / PIB)            [fetch pipeline: not yet built]
        |
        v
   db/dpdpa.db  (SQLite — source of truth; full clause text lives here)
        |
        +---> src/export_word.py  --> docs/DPDP_Rules_2025.docx
        |                         --> docs/DPDP_Act_2023.docx
        |                             (legal-style layout, bookmarked,
        |                              amendment highlighting)
        |
        +---> src/export_excel.py --> data/DPDP_Rules_Tracker.xlsx
                                      (Master_Provisions/Change_Log/
                                       Source_Log — links jump straight
                                       into the docx above)
```

SQLite holds the real, current state, **including the verbatim clause
text** (`provisions.full_text` — no paraphrasing, no abridging). The Excel
workbook and the two Word documents are both *generated from* SQLite —
don't hand-edit them expecting it to persist; re-running the export
scripts will overwrite them.

**Amendment convention:** once the pipeline detects and a human approves a
real change, `export_word.py` renders it into the docx with the new text
highlighted yellow and the superseded text struck through directly below,
under a "Previous text (superseded)" label. This is dormant on the initial
baseline load (everything is `change_type = 'New Provision'`) but is
already wired up for when real changes start flowing through.

## Project layout

```
config/         source list, check frequency (to be added)
db/
  schema.sql    table definitions (provisions, change_log, source_log)
  dpdpa.db      the actual database (gitignored — generated locally)
docs/
  DPDP_Rules_2025.docx   generated consolidated Rules document
  DPDP_Act_2023.docx     generated consolidated Act document
  full_text/     OBSOLETE — leftover from an earlier design (small .md
                 files per provision). Safe to delete; full text now
                 lives in the database and is rendered into the two
                 docx files above instead.
data/
  DPDP_Rules_Tracker.xlsx   generated Excel view (gitignored)
src/
  db.py                     connection + schema init helper
  init_db.py                creates db/dpdpa.db from schema.sql (empty)
  seed_dpdp_rules_full.py   loads all 23 Rules + 7 Schedules (verbatim)
  seed_dpdp_act_full.py     loads all 44 Act sections + penalty Schedule
  export_word.py            SQLite -> the two consolidated .docx files
  export_excel.py           SQLite -> the Excel tracker
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt   # use python -m pip if pip.exe is Device-Guard-blocked
copy .env.example .env        # then fill in OPENROUTER_API_KEY
```

## Usage so far

```bash
python src\init_db.py                    # empty schema
python src\seed_dpdp_rules_full.py       # load the 31 Rules provisions
python src\seed_dpdp_act_full.py         # load the 47 Act provisions
python src\export_word.py                # generate the two Word docs
python src\export_excel.py               # generate the Excel tracker
```

Total after both seeds: 78 provisions (31 Rules-side + 47 Act-side).

## Review workflow

Any detected change lands in `change_log` with `review_status = Pending
Review`. Nothing updates `provisions` (the current-state table) until a
human sets `review_status = Approved`. This is deliberate — a compliance
tool that silently auto-applies AI-interpreted legal changes is worse than
one that asks a human to glance at anything non-trivial first.

## Not yet built

- Fetching from MeitY / eGazette / PIB
- PDF/HTML extraction
- OpenRouter-based classification (which provision, what changed, confidence)
- Diffing against existing `provisions` rows
- Scheduling (cron / Task Scheduler)
- RBI half of the project
