# DPDPA / RBI Regulatory Change Tracker

Automation project to keep consultants current on DPDP Act, 2023 / DPDP
Rules, 2025 (and later, RBI) updates without manual monitoring.

**Current scope:** DPDP Act + Rules baseline loaded (all 48 Act rows and
31 Rules rows verbatim from the official PDFs), and the daily
fetch/classify/apply/notify pipeline is built and running. RBI comes
later once this half is proven out in production.

## Architecture

```
MeitY Rules PDF --------\    (the only two sources allowed to
MeitY Act PDF -----------+--> change stored legal text)
PIB (RSS, alert-only) --/   src/fetch_sources.py --> source_log (hash-based
                                                      change detection)
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
                 bookmarked, amendment                    straight into the docx,
                 highlighting, provenance                 relative to the workbook)
                 + "not legal advice")

src/run_pipeline.py orchestrates all of the above; src/notify.py sends one
summary email per run (Gmail SMTP) regardless of whether anything changed.
.github/workflows/daily-check.yml runs the whole chain on a daily cron and
commits db/docs/data back to the repo.
```

Separately (added 30 Sep 2026), `src/discover_documents.py` watches pages that
*list* documents — eGazette's Ministry of Electronics & IT search, currently —
and alerts by email when a brand-new document appears. This is a different
job from the pipeline above: fetch_sources.py only notices when one of its
four known URLs is *edited*, which real amendments and corrigenda almost
never are (they're published as separate, brand-new documents instead — the
"Not yet built"/"Document discovery" sections below explain why, and
`docs/detection_coverage_2026-09-30.md` has the full investigation). It never
writes to `provisions`/`change_log` — see that section for what it does
instead.

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

**EVERY government change to a provision is shown, not just the latest one.**
`export_word.fetch_amendments` asks `change_log` for every applied
`regulatory` change to a provision, newest first, and both exporters use that
one query so they can never disagree. Each change is highlighted at every
place its changed words appear, and the caption names each one; the
`Last_Regulatory_Change` cell shows the newest and adds "(+N earlier)" when
there is more history behind it.

This replaced a version that followed `provisions.latest_change_id` and then
checked whether what it found was `regulatory`. That had two faults the audit
found. A data correction applied *after* a real amendment moved the pointer,
the check rejected it, and the amendment's highlighting, caption and Excel
cell all vanished without a word (**H-6**) — so the old README claim that data
corrections "never affect rendering" was false: they erased an earlier
amendment's rendering. And because only one row was ever returned, a provision
amended twice looked as though it had been amended once (**M-1**). The rule as
written now holds: **a data correction never changes what the documents show as
a change in the law.**

### What the generated files say about themselves

Both Word documents carry, at the top: the date they were last regenerated, the
date the text is accurate as at, the date of the most recent government change
recorded in them, and the sentence **"This is a reading copy generated from the
project database. It is not legal advice. Verify any clause you quote against
the official Gazette."** The Rules document also says that it incorporates
Corrigendum G.S.R. 892(E) of 10 December 2025, whose corrections its text
carries (audit finding L-8 — a document that may reach a client needs to say
what it is).

The Excel tracker's "Open full text" links are **relative to the workbook**
(`../docs/DPDP_Rules_2025.docx#DPDPR_R23`), so they work for whoever opens the
file. Every one of the 79 links used to be an absolute path on whichever
machine generated the workbook — in the committed file, a folder inside a past
AI session's sandbox that has never existed on anyone's computer (audit finding
H-4). The links only start working once the workbook is regenerated.

## Sources & change detection

Three sources are fetched daily. They are **not** equally trusted, and
since 30 Sep 2026 that difference is enforced in code, not just described
here — see "Which source may change which law" below.

1. **MeitY** — the two known static PDF paths (DPDP Rules 2025, DPDP Act
   2023). These are the only trustworthy sources, because they are the
   official documents themselves at direct file URLs, and they are the
   only two allowed to change stored legal text. (MeitY does have two
   pages listing DPDP documents, which would catch a *new* notification or
   corrigendum that these two fixed PDF URLs can't — but they're Next.js
   single-page apps with no server-rendered content, and a real headless
   browser gets blocked outright (HTTP 403) by the site's own
   bot-detection. Investigated twice now, genuinely not reachable either
   way — see `fetch_sources.py`'s header comment and
   `docs/detection_coverage_2026-09-30.md`.)
2. **PIB** — an RSS feed (`RssMain.aspx?...&lang=1`), explicitly
   parameterised to English. This replaced scraping PIB's HTML "all
   releases" page, which could silently serve Hindi depending on the
   requesting client's apparent locale with no way to confirm what
   language GitHub Actions' server would see. **PIB is a coincidence
   detector, not a reliable source.** A press release is not a legal
   instrument: it can tell you that something DPDP-shaped has happened, it
   can never tell you what the law now says. So when a PIB headline
   matches the DPDP keywords, the pipeline makes **no AI call** and simply
   adds an alert line to the daily email ("PIB mentions data protection:
   *title* — go and look") for a human to follow up.

**Retired 30 Sep 2026 — the eGazette home page** (`https://egazette.gov.in/`)
was a third fetched source. It was meant to be the authoritative
confirmation source, but its real notification search is a session-scoped
ASP.NET postback form with no stable endpoint, so all it ever did was hash
the home page. That signal reported "changed" on 20 of 23 recorded
production days and produced a real change on none of them — a 100%
false-positive rate that also spent an AI call every single day for
nothing — while still being a page whose text could in principle reach
stored legal text. It is no longer fetched or classified. Its actual job,
noticing a brand-new Gazette document, is now done properly by the
document-discovery layer below, which drives eGazette's own "Search by
Ministry" form and only ever raises an alert. Its `source_log` row is kept
(it carries change history) but marked `watched = 0` by
`scripts/mark_unwatched_sources_2026-09-30.py`.

TLS certificate verification is **no longer switched off for any host**.
eGazette chains to a root that Windows trusts but the `certifi` bundle does
not, which used to be worked around by disabling verification for that one
host. The chain is now pinned in `certs/egazette-chain.pem` and verified
against it. `certs/README.md` holds the fingerprints, how they were
cross-checked, and the runbook for when the pinned root changes.

### Which source may change which law (the source-authority rule)

Both verbatim checks in `classify_change.py` require the new legal text to
appear in the *fetched content* — which is exactly the text whoever
controls that page controls. The 30 Sep 2026 audit demonstrated the
consequence end-to-end against the real production model: a forged
"notification" appended to a watched page was accepted and written into
`provisions.full_text`. The model behaved correctly; the system simply had
no way to tell a real Gazette notification from text that merely appears
on a Gazette web page.

So each source now carries a `may_amend` list in `src/fetch_sources.py`
naming the provision IDs it is permitted to change:

| Source | May change |
|---|---|
| MeitY — DPDP Rules 2025 PDF | `DPDPR-*` only |
| MeitY — DPDP Act 2023 PDF | `DPDPA-*` only |
| PIB feed | nothing — alert only |
| anything else, now or in future | nothing — alert only |

The rule **fails closed**: a URL that isn't listed gets an empty list, so
any source added later is alert-only until someone deliberately grants it
authority. It is enforced twice, in `classify_change.classify()` and again
in `apply_change.apply()`, so a mistake in one place cannot undo the other.
A refused change is never silently dropped — it is reported as an error, so
it reaches the run's exit code and the daily email.

`fetch_sources.py` hashes *extracted, cleaned text* (not raw bytes) so PDF
metadata churn and HTML analytics-script noise don't cause false-positive
"changes." Each source has exactly one row in `source_log` (its `url`
column is `UNIQUE`) that gets updated on every fetch, not a new row per
run. A source that is no longer watched — a one-off Gazette PDF fetched by
hand, a page that has been retired — keeps its row, because that row records
which change came from where, and is marked `source_log.watched = 0` instead.
**The Excel Source_Log sheet shows only `watched = 1` rows**, so it really does
show what is being watched right now. (Before 30 Sep 2026 it showed all seven
rows while describing itself as "what's being watched right now", when only
three were — audit finding M-5. The flag is set by
`scripts/mark_unwatched_sources_2026-09-30.py`.) A download failure keeps the
last known-good fingerprint
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
a `change_log` row is written by the pipeline as `Approved` by `auto` — it
is **not** a queue waiting for a consultant's sign-off. (Separately, on
29 Sep 2026 Gautam reviewed every row that existed then by hand, so the
current 79 provisions and 142 change rows do carry a real human sign-off;
anything the pipeline adds from now on does not.) If a human check *before*
a change goes live is wanted, that would need to be a deliberate change to
the pipeline; right now, it isn't there.

What does constrain auto-apply is the source-authority rule above: a change
is only ever applied if it came from the official document for that
instrument. Nothing else can write legal text, whatever it appears to say.
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
                     source_snapshot, discovered_documents, discovery_run_log)
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
  fetch_sources.py          fetches the two MeitY PDFs + PIB, hash-based change
                             detection; also holds the may_amend authority table
  discover_documents.py     alert-only: watches document *listings* (eGazette
                             ministry search) for brand-new documents; never
                             touches provisions/change_log — see "Document
                             discovery" above
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

## Heartbeat — how you find out if the whole thing goes quiet

A **heartbeat** is a small "I'm alive" signal the daily job sends to an outside
service every time it finishes. If that service stops hearing from it, *the
service emails you*. It is the alarm that fires when a signal **doesn't**
arrive, which is the one kind of alarm this project could not raise for itself.

**Why it is needed.** Every warning this project produces travels down exactly
one channel: the daily summary email over Gmail. That channel can itself fail,
and when it does the result is silence — which looks exactly like a quiet day
with no changes. All of these produce silence, and none of them could tell you:

| What goes wrong | What you would have seen before |
|---|---|
| The Gmail app password expires or is revoked | Nothing, indefinitely |
| The daily `git push` is rejected | An email that says nothing about it |
| GitHub disables the schedule (it does this to public repositories after 60 days of no activity) | Nothing |
| The job crashes before it can send anything | Nothing |

**What it does and does not cover.** It covers all four of the above, because
it is the *absence* of the ping that raises the alarm. It does **not** tell you
anything about the content of a run — a run that succeeds but finds nothing
still pings normally. It is a liveness check, not a correctness check.

**Setting it up (about five minutes, and free).**

1. Go to <https://healthchecks.io> and create a free account. (cron-job.org and
   several others work the same way; the instructions below are for
   healthchecks.io.)
2. Click **Add Check**. Name it something like `DPDP daily check`.
3. Set **Period** to `1 day` — how often it should expect to hear from the job.
4. Set **Grace Time** to `6 hours`. GitHub's scheduler can start a job hours
   late, and a false alarm every time it does would teach you to ignore the
   real one.
5. Make sure the check's email notification is switched on and pointed at your
   address.
6. Copy the check's **ping URL**. It looks like
   `https://hc-ping.com/` followed by a long random string. **Treat it as a
   password** — anyone with it can pretend to be your job.
7. In GitHub, go to the repository → **Settings** → **Secrets and variables** →
   **Actions** → **New repository secret**. Name it exactly `HEARTBEAT_URL`,
   paste the ping URL as the value, and save.
8. Go to the **Actions** tab → "Daily DPDP regulatory change check" → **Run
   workflow**. When it finishes, healthchecks.io should show the check as "up"
   with a ping just now.

Until that secret exists, the workflow still runs normally and prints a visible
warning in the job log saying the heartbeat is not set up. It never fails the
job over it, and it never prints the URL itself.

**If a run fails**, the workflow pings `<your ping URL>/fail` instead, which
healthchecks.io treats as "this job ran and went wrong" and alerts on
immediately rather than waiting for the next missed ping.

## Document discovery — what happens when a *new* document appears

Real DPDP law changes almost never edit one of the four URLs above — they show
up as brand-new, separate documents instead (the December 2025 corrigendum to
the Rules is the real example that motivated this: the original Rules PDF was
never touched). `src/discover_documents.py` is a second, separate layer for
exactly this case: it watches pages that *list* documents — right now,
eGazette's "Search by Ministry" filtered to the Ministry of Electronics & IT
(driven with a real, invisible Chrome browser via Playwright, since that
search is a multi-step form) — and remembers what it's already seen.

**This layer is alert-only.** A newly discovered document never touches
`provisions`, `change_log`, the Word files, or the Excel tracker — it has no
prior version to diff against, and this project's rule that legal text must
come from a PDF through code (never typed or guessed) means a human has to
decide what to do with it. See `scripts/apply_rules_corrigendum_2026-09-23.py`
for what that "a human decides, with Claude's help" step actually looks like
in practice.

**What to expect on the very first run for a new source:** everything it
currently lists gets quietly recorded as a starting point ("baseline
captured for egazette-meity: N document(s)" — one line in the normal daily
email) — not a flood of alerts about documents that were already there.
**From the next run onward:** if something new and DPDP-relevant shows up,
the day's email subject starts with `ACTION NEEDED — new DPDP-related
document found`, and the body lists the document's title, source, date,
link, and a short excerpt of its text, with the reminder that nothing in the
database has changed automatically. If a newly-found document's PDF can't be
read for some reason, it's still alerted (never silently dropped) — just
without an excerpt.

**Three checks stop a quiet failure looking like "nothing new" (audit M-6,
M-7, M-12):**

- The eGazette results page prints its own total ("Total No. of Gazettes : 5").
  That number is read and compared with the number of rows actually scraped. If
  they disagree the run **fails loudly**, because a half-read listing and a
  genuinely empty month look identical from the outside.
- One badly-formatted Gazette ID used to make the whole day's listing
  unusable. Now the good rows are kept, and the bad one is named in the day's
  errors with a "please look this one up by hand" note.
- The search is scoped to calendar months, so an outage longer than its normal
  two-month window meant whole months were never looked at again by any later
  run. When the last successful discovery run is more than 25 days old the
  window widens to cover everything since that run — capped at 12 months, with
  a pause between months to stay polite, and the widening is always reported.
  Anything older than the cap is named as **not** checked.

## Not yet built

- A stable, verified eGazette search/filter endpoint **for the main daily
  fetch/classify pipeline above** — separate from the discovery layer,
  which does have a working eGazette search now (see above). The old,
  coarse home-page hash that `fetch_sources.py` used instead was retired on
  30 Sep 2026 rather than replaced (see "Sources & change detection"), so
  the daily fetch/classify pipeline now has no eGazette signal of its own.
  That is a deliberate trade: the signal it gave was wrong 100% of the time
  it fired, and the discovery layer covers the same ground honestly.
- MeitY's own DPDP-documents listing pages, for the same reason as above —
  investigated for discovery too, genuinely blocked (see "Sources & change
  detection").
- RBI half of the project

## Known limitations

- **No human review gate** on auto-applied changes — by design, not an
  oversight; see "Classification & auto-apply" above. Whether to add an
  approval gate is Gautam's and EY's decision, deliberately left open
  rather than guessed at.
- **Court orders and Data Protection Board orders are not watched at all.**
  Sections 11 and 12 of the Act (a Data Principal's rights, and the Board's
  powers) can be shaped in practice by Board orders and by court judgments,
  and nothing in this project looks for either. There is no automated
  source for them here and none is planned — assume they are unmonitored
  and check them by hand if they matter to a question you are answering.
- **`confidence_score` is recorded but does not gate anything.** Every
  AI-classified change stores the model's own confidence, and a low score
  does *not* stop a change being applied. This is deliberate: the audit
  measured a genuine, correctly-identified amendment at 0.65, so a
  threshold would have blocked a real change. Treat the number as a hint
  when reviewing, not as a safety mechanism.
- **MeitY's own document-listing pages return HTTP 403** to anything that
  is not a human with a browser, so they cannot be watched directly and no
  attempt is made to work around it (this project does not bypass any site's
  protections). Everything MeitY publishes is therefore seen only through
  eGazette's ministry search, or not at all.
- **If MeitY re-publishes a document at a new URL, that is invisible to the
  four fixed sources.** They are watched by address: a new address is a new
  document, which only the discovery layer might notice, and only if it also
  appears in eGazette's MeitY listing. This is not hypothetical — MeitY has
  still never corrected the Rules PDF itself, ten months after the corrigendum,
  so the corrigendum only ever existed as a separate document.
- **An amendment made by a ministry other than MeitY would not be found.**
  eGazette's search is filtered to the Ministry of Electronics & IT. A DPDP-
  relevant change issued by another ministry, or by a body publishing outside
  the Gazette, is outside everything this project looks at.
- **The distributed Excel file's "Open full text" links do not work until the
  workbook is next regenerated** — see H-4 above. The fix is in the code; the
  committed `.xlsx` still holds the old absolute paths.
- **The Fourth Schedule Note's corrigendum relabelling is captioned, not
  highlighted.** Corrigendum G.S.R. 892(E) item (v)(b) relabels a run of items
  that spans several paragraphs, and the renderer only highlights text it finds
  whole inside one paragraph — deliberately, so it can never highlight the
  wrong words. That change is named in the provision's caption and is a yellow
  row in the Excel Change_Log; it just has no yellow words in the Word file.
- **Two run-in separator dashes in the Fifth Schedule are still missing.** The
  Gazette prints `namely:-` in two places where the database has `namely:`.
  They are recorded as reviewed exceptions in
  `tests/test_legal_text_verbatim.py`; the 30 Sep 2026 restore script fixed the
  15 numbered-heading dashes it was scoped to and deliberately left these two.
  A small follow-up.
- The document-discovery layer only watches MeitY notifications via
  eGazette — PIB was investigated as a second discovery source and ruled
  out (its feed holds only 20 items across every ministry, with no date on
  each item, and no stable MeitY-only version of it could be found); MeitY's
  own listing pages are blocked outright (see above). A DPDP-relevant
  document published somewhere neither eGazette's ministry search nor these
  four fixed sources would ever see could still be missed.
