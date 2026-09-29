# Detection coverage — can the daily run discover *new* DPDP documents?

**Date:** 2026-09-30. **Cost:** $0 (nothing here calls a paid AI — this is all plain
Python, HTTP requests, and a headless browser).

**Plain-words summary of the problem:** the daily check only re-reads four pages it
already knows about and looks for edits. Real Indian law changes don't edit old PDFs —
they get published as brand-new, separate documents (a "corrigendum", i.e. an official
notice fixing a printing mistake in an earlier notice, is a good example: the December
2025 fix to the DPDP Rules never touched the original Rules PDF at all). So the daily
check would never have noticed it. This document records what we tried to fix that,
what worked, what didn't, and why.

A few terms used below: a **headless browser** is a real web browser (Chrome) that runs
without a visible window — used here because some government pages only build their
content with JavaScript after the page loads, which a simple "fetch this URL" request
can't see. A **WAF** ("web application firewall") is a security layer in front of a
website that can block traffic it thinks looks automated, independent of anything in
the request's headers. A **CAPTCHA** is the "click all the traffic lights" puzzle sites
use to prove a human is present — we were told never to try to solve or bypass one.

---

## A1 — Can Playwright (a headless-browser tool) run on this PC?

**Yes.** `python -m pip install playwright` and `python -m playwright install chromium`
both completed cleanly in `.venv`, and a smoke test (`browser.goto("https://example.com")`)
returned the page title correctly. This is a change from what earlier sessions found for
`fitz`/PyMuPDF (still blocked) — Playwright's browser binary is not blocked by this
machine's Device Guard policy. This means browser-based discovery code is allowed to
ship per the task's own rule ("don't ship browser code you couldn't run locally") — but
see A2, where the browser runs fine and still gets blocked by the *target site*, which
is a different kind of stop.

## A2 — MeitY document-list pages: not usable, by either method

Checked both `https://www.meity.gov.in/data-protection-framework` and
`https://www.meity.gov.in/documents/act-and-policies`.

**Plain `requests.get`:** returns HTTP 200, ~3.2 KB of HTML. Inspecting it: this is a
statically-exported Next.js site (`"nextExport":true` in the page's own
`__NEXT_DATA__` block, build ID `fpqxHBFoRnMPDSx6r14eA`, route `/[parentslug]`). The
document list is not in this HTML — it's built by JavaScript after the page loads, so a
plain request can never see it.

**Next.js's own JSON data paths:** for a statically-exported Next.js site, page data is
sometimes available at `/_next/data/<buildId>/<path>.json`. Tried both pages' equivalent
— both returned HTTP 200 but with the *same 3.2 KB HTML shell*, not JSON. Dead end.

**A sitemap:** `https://www.meity.gov.in/sitemap.xml` exists and is plain-GET, but it
only lists 50 *page routes* (e.g. `.../documents/act-and-policies?page=3`), not the
individual documents or PDFs those pages contain once JavaScript renders them. No
document data here either.

**Playwright (real headless browser):** loading either page with a real Chromium
browser returns **HTTP 403 "Access Denied"** — even using Playwright's own default,
completely standard Chrome user-agent string (i.e. this is not about our identifying
`DPDPAChangeMonitor/1.0` User-Agent — a real, ordinary Chrome fingerprint gets the same
block). This is a WAF blocking automated/headless browser traffic specifically, not a
missing-JavaScript problem. Per the hard rule — never try to solve or bypass a CAPTCHA,
login, rate limit, or block — **this is exactly that kind of block, so it was not
pursued further** (no stealth plugins, no proxy tricks, no header spoofing beyond what
a real browser already sends).

**Conclusion: not feasible.** Plain requests see no data; a real browser is blocked by
the site itself. Both routes were tried in good faith and both are genuine dead ends,
not a 45-minute-timebox give-up. **MeitY document-list discovery is not being built.**
This is a real, documented gap: if the government publishes something new only on these
two pages (not via PIB or eGazette), this pipeline still won't see it. Flagged as a
follow-up for whoever next revisits this (a non-headless "real Windows Chrome, driven by
a person" run, or contacting MeitY's webmaster for an API, are the only remaining ideas,
and both are out of scope for an unattended daily job).

## A3 — eGazette search: works, no CAPTCHA, and finds the known corrigendum

`egazette.gov.in`'s real search (`SearchMenu.aspx` → "Search by Ministry") is an
ASP.NET web form (a login-free per-visit session ID is baked into the URL path, e.g.
`/(S(abc123...))/SearchMinistry.aspx`; submitting the form works by "postback" —
picking an item from a dropdown reloads the page with more options, same page,
same session). Using Playwright to click through it:

1. Home → "Search" → "Search by Ministry" — a plain page, **no CAPTCHA anywhere in this
   flow** (checked visually with a screenshot and by searching the rendered page text
   for "captcha").
2. Pick Ministry = "Ministry of Electronics and Information Technology" (one of 607
   options in one long dropdown — it lists every government body, not just top-level
   ministries), Month = December, Year = 2025, click Submit.
3. Result: a 5-row table. **Row 2 is exactly the known answer**: *"Notification
   Extraordinary of Corrigendum to the Digital Personal Data Protection Rules 2025 for
   publication in Part II Section 3 Sub Section i of the Gazette of India"*, Issue Date
   11-Dec-2025, Publish Date 12-Dec-2025, Gazette ID `CG-DL-E-12122025-268455`.
4. Clicking each row's download icon opens a small popup window whose network request
   is a **static, session-free PDF URL**: `https://egazette.gov.in/WriteReadData/<year
   >/<the numeric tail of the Gazette ID>.pdf` — e.g. row 2 above is
   `https://egazette.gov.in/WriteReadData/2025/268455.pdf`. **Verified this pattern
   against two more rows independently** (row 1's `CG-DL-E-18122025-268622` →
   `.../2025/268622.pdf`, row 3's `...268316` → `.../2025/268316.pdf`) — both downloaded
   real PDFs with plain `requests`, no browser, no session. This matters a lot: the
   *search* needs a browser (to work through the postback form), but once we have a
   Gazette ID from the results table, the *download* never does.
5. **Independently verified correct**: downloaded `.../2025/268455.pdf` with plain
   `requests` and hashed it — **SHA-256 `8f8d9526b511801889f8ae022b6d7c5db449283e90fe
   32792e5896314b32f994`**, which is byte-for-byte the same hash the 23 Sep 2026 audit
   already recorded for this exact corrigendum from an independent download. Two
   separate sessions, two independent downloads, identical file.
6. Result-table fields (for the fetcher to read): S.No, Ministry/Organization,
   Department, Office, Subject, Category, Part & Section, Issue Date, Publish Date,
   Gazette ID, Download link.

**No `robots.txt` restriction found** (`egazette.gov.in/robots.txt` returns a plain
404 — meaning there is no robots file at all, so no rule to check against).

**A real limitation, not a bug:** this search is scoped to one calendar month at a
time (a "Month/Year" search, not a date-range or "everything" search) — see the
canary-design note in the Build section below for how this shapes the discovery code.

**Conclusion: feasible, and built** (see Phase B). This is the one new discovery source
that actually catches the December 2025 corrigendum.

## A4 — PIB feed: confirmed thin, no MeitY-only alternative found

The feed the pipeline already reads (`RssMain.aspx?ModId=6&Mid=0&reg=3&lang=1`) holds
**exactly 20 items at any moment**, covering *every* ministry's press releases, not just
MeitY's. Worse: each `<item>` has only a `<title>` and a `<link>` — **no date field at
all** — so there's no way to even measure "how far back in time" those 20 items reach;
all we know is it's the newest 20, whatever that spans on a busy news day. This
confirms the concern: with dozens of ministries publishing releases through one shared
20-item window, a single relevant MeitY release could easily be pushed out before the
next day's run ever sees it.

Looked for a MeitY-only version of the feed (a different `Mid=` value): PIB's ministry
dropdown wasn't found in either `allRel.aspx` or `PressReleasePage.aspx` (the latter
404s; the former's HTML has no "Electronics" or ministry-list markup at all — likely
also JavaScript-rendered). **No stable MeitY-only feed found.** Per the task's own rule
("only change the PIB source if you can prove the replacement is better"), **PIB is
left exactly as it is** — this is a documented, unresolved weakness, not a fix.

---

## What this adds up to (before the Build section below)

| Source | Listable at all? | Needs a browser? | Finds the known corrigendum? |
|---|---|---|---|
| MeitY document lists | No (blocked/JS-only both ways) | N/A — not usable | No — can't be checked |
| eGazette ministry search | Yes | Yes, for the search step only | **Yes**, confirmed |
| PIB (existing source) | Yes (already used) | No | Not applicable — unchanged, still weak |

One new, real discovery source (eGazette) is buildable and demonstrably catches the
real-world case this task is about. MeitY stays an open gap. PIB stays unchanged
because no better replacement was found. Per the task's own instruction, this is enough
to be worth building (not "nothing is feasible") — continuing to Phase B.

---

## Phase B — what was built

**`db/schema.sql`**: two new tables, exactly as specified, added with `CREATE TABLE IF
NOT EXISTS` (never alters an existing table) — `discovered_documents` (one row per
document ever seen, keyed by its permanent URL) and `discovery_run_log` (one row per
"listing checked", used only for the canary below).

**`src/discover_documents.py`** — the new module. `DISCOVERY_SOURCES` currently has one
entry, `egazette-meity`, driven by Playwright as described in A3. Key design points
that came from testing against real data, not just the written spec:

- **The stored `url` is always the permanent `WriteReadData` PDF link, never the
  session-scoped search URL** (that URL contains a `(S(...))` token that changes on
  every visit — using it as the primary key would mean "alert once" silently became
  "alert every single day forever" for the same document, which would have been a
  serious, easy-to-miss bug).
- **The eGazette search is scoped to one calendar month**, so the discovery run checks
  the current month and the previous one every day (a rolling ~2-month window). This
  changed the canary design from the spec's literal wording: comparing "today's count"
  to "yesterday's count" across a whole source doesn't work when the source's own
  month window shifts — the 1st of every month would look like a false "listing
  broke" (its current-month count legitimately resets near zero). Instead,
  `discovery_run_log` gets one row **per month queried** (`discovery_source` holds a
  key like `egazette-meity:2026-09`), and the "0 items" / "under half of last time"
  checks only ever compare a month against its own most recent prior count — never
  across different months. A month with no prior count yet (first time queried, or
  its only prior count was itself 0) is never flagged. This is the one deliberate
  deviation from the literal spec wording, made because the literal version would
  have produced a guaranteed false alarm every month.
- A related bug found only by writing the tests (Phase C): checking "is this source
  new" by counting rows in `discovered_documents` breaks if a source's very first-ever
  run happens to find zero documents — it would look "uninitialized" forever and
  silently re-baseline (swallowing) everything found on every future run instead of
  alerting. Fixed by tracking "has this source ever run" as its own dedicated,
  namespaced row in `discovery_run_log`, separate from the per-month canary rows.
- **A failed email must not lose a document.** `alerted` only flips to 1 after
  `notify.send_summary()` returns successfully (`run_pipeline.py` calls
  `mark_alerted()` only then). Every run, before looking for brand-new documents, the
  module first re-offers anything already stored but still `alerted=0` — so a failed
  send is retried next run, not silently dropped. Telling "still waiting to be sent"
  apart from "was read and correctly judged not relevant" (both would otherwise show
  `alerted=0` forever) needed one more small trick within the given schema: an
  unreadable PDF's `text_excerpt` is stored as the literal string `[could not be
  read]` instead of null, which both drives the "could not be read" email wording and
  lets a retry tell "still pending" apart from "genuinely irrelevant."
- **English-only excerpts** reuse `classify_change.py`'s existing Devanagari-share
  check (`_is_mostly_hindi`) rather than a new one — Gazette PDFs are bilingual, and
  that function already does exactly this job for the daily classifier.

**`src/run_pipeline.py`**: calls `discover_all()` after `fetch_all()`, wrapped in its
own try/except so a discovery failure is appended to `errors` and never stops the
existing fetch → classify → apply flow. `send_summary()` gets two new, optional
keyword arguments (`new_documents`, `baseline_notes`) with safe defaults, so every
existing caller and test keeps working unchanged.

**`src/notify.py`**: when there are new documents, the subject always starts with
`ACTION NEEDED — new DPDP-related document found` — this wins over every other subject
wording, so a reader skimming only the subject can't miss it (the same principle
behind the existing error-subject fix from the 23 Sep audit). The body's first section
lists each document (title, source, date, link, excerpt) plus "Nothing has been
changed in the database — please review this document." Baseline notes go in the
normal body. Existing no-new-documents behaviour is unchanged (checked by test).

**Playwright in CI**: `requirements.txt` pins `playwright==1.63.0` (the exact version
verified locally); `.github/workflows/daily-check.yml` gets one new step,
`python -m playwright install --with-deps chromium`, before "Run pipeline" — the pip
package alone does not include the browser binary. The existing
`git add db/dpdpa.db docs/*.docx data/*.xlsx` / `if: always()` commit step is
untouched.

---

## Phase D — proof against the real world (read-only)

Run against a **throwaway copy** of `db/dpdpa.db` (never the live file), with
`--dry-run` (writes nothing even to the copy, so it's repeatable).

**1. Full pipeline, current window (today = 30 Sep 2026 → checks September and August
2026):**

```
python src/discover_documents.py --dry-run --db <copy>
[baseline] baseline captured for egazette-meity: 3 document(s)
```

Took ~40 seconds. First-ever run on this copy, so — correctly — a baseline, not
alerts. The 3 real documents behind that baseline (fetched directly to inspect them):

| Date | Subject | DPDP-related? |
|---|---|---|
| 2026-09-21 | Amendment to the Electronics and IT Goods (Compulsory Registration) Order | No |
| 2026-08-31 | Semicon — Scheme for Semiconductor Design and Manufacturing Ecosystem | No |
| 2026-08-21 | Notification re: a Ministry matter, Part I Section 1 | No |

**Honest framing: this run does NOT include the December 2025 corrigendum**, and it
was never going to — the search is month-scoped and today is 30 September 2026, seven
months after the corrigendum was published. A live run today can only ever prove
"nothing DPDP-related happened in the current window," which is genuinely all it
claims. **If read as "the live run found the corrigendum," that would be wrong — it
did not, because the corrigendum is outside any window this run could reach.**

**2. One-off, separate check that the source itself surfaces the corrigendum when its
window covers it** (not part of the daily production window — this calls the exact
shipped `_egazette_search_month()` function directly for December 2025, to prove the
*source*, not just a fixture, produces the known answer):

```
5 rows found in 13.9s
 - CG-DL-E-18122025-268622 | 18-Dec-2025 | .../2025/268622.pdf | Hindi Advisory Committee resolution
 - CG-DL-E-12122025-268455 | 11-Dec-2025 | .../2025/268455.pdf | Notification Extraordinary of Corrigendum
   to the Digital Personal Data Protection Rules 2025...
   >>> KNOWN-ANSWER MATCH (G.S.R. 892(E) corrigendum)
 - CG-DL-E-08122025-268316 | 04-Dec-2025 | .../2025/268316.pdf | Cyber Forensics Labs notice
 - CG-DL-E-05122025-268267 | 04-Dec-2025 | .../2025/268267.pdf | Cyber Forensics Labs notice
 - CG-DL-E-05122025-268254 | 04-Dec-2025 | .../2025/268254.pdf | Cyber Forensics Labs notice
```

Confirms the same result found during Phase A research, using the actual shipped code
this time rather than an ad-hoc script.

**3. The full alert pipeline (baseline → a later run that includes the corrigendum →
exactly one alert) is proven by the automated replay test**
(`tests/test_discover_documents.py::test_corrigendum_replay_is_found_via_pdf_text_not_
title_or_url`), using the real, committed corrigendum PDF and a listing built to match
what eGazette's real page actually looked like on 11 Dec 2025 — a hashed-filename URL
and a neutral title containing no DPDP keyword, exactly the MeitY-style problem this
whole task is about. That test passes.

**Put together, honestly: the source can list the corrigendum (proof 2), and the
alerting logic correctly catches it when it's listed (proof 3) — but no single run in
this project, live or otherwise, has "found the corrigendum today," because today's
real-world window doesn't reach December 2025. If this system had been running back
in December 2025, proof 2 shows it would have listed the document, and proof 3 shows
it would then have alerted on it.**

---

## Phase G — the first real GitHub Actions runs, and three real production failures

Merged to `main` on 30 Sep 2026. Everything above was proven on Gautam's own Windows
PC — the real GitHub Actions environment turned out to behave differently, in a way
worth recording honestly since it took three attempts to actually fix.

**Failure 1** (first-ever real daily run): `Page.goto: Timeout 30000ms exceeded`
navigating to `https://egazette.gov.in/`. A 30-second timeout on a slow site — this
project already knew eGazette was slow (`fetch_sources.py`'s plain-HTTP timeout was
bumped 30s→60s back on 25 Sep for the same host), just hadn't applied that lesson to
the new Playwright code yet. **Fix:** raised every timeout in the new eGazette flow to
60s, and switched from `wait_until="networkidle"` (which needs 500ms of *zero* network
activity — easy for a page with any background request to never satisfy) to `"load"`.

**Failure 2** (second real run, after Fix 1): `Page.goto: Timeout 60000ms exceeded`,
same URL, same wait condition — even 60 seconds of "load" wasn't enough. The
discriminating fact: this exact URL is already fetched successfully **every single
day** by a plain `requests.get()` call in `fetch_sources.py`, in well under a second,
from this same GitHub Actions environment. So the connection and the site were never
the problem — waiting for the browser's generic "everything on this page is fully
loaded" signal was. **Fix:** stopped waiting for a page-wide signal at all. Switched to
`wait_until="commit"` (only waits for the response to start arriving) and made every
later step wait for the one specific DOM element it actually needed next (the ministry
dropdown, the results label) — Playwright's `click()`/`select_option()` already do this
automatically for their own target, so this removed the dependency on anything
page-wide finishing.

**Failure 3** (third real run, after Fix 2): `Page.click: Timeout 60000ms exceeded`
clicking "Search by Ministry" — but the call log showed it was actually still stuck
waiting for the *earlier* navigation to `default.aspx` to finish, not for the click's
own target to appear. In plain words: the document itself had already arrived (Fix 2
worked for that part), but the browser was still busy loading *something else* on that
page in the background, and Playwright's own safety check for the next click was
waiting for that unrelated background loading to settle first before proceeding.

At this point, two different fixes were considered (both discussed with a second
opinion before building either, given three failures in a row was enough to stop
guessing blindly):

- Drop the headless browser for this source entirely and replicate eGazette's form
  submission with plain `requests` instead, since the same host's plain HTTP requests
  were already proven reliable. **Investigated, not used**: `SearchMinistry.aspx`
  turned out to need visiting `SearchMenu.aspx` first in the same session (a real,
  confirmed, but shallow requirement — not a token to break, just a navigation-order
  check) — but reconstructing the exact ASP.NET postback (all the hidden `__VIEWSTATE`
  fields, in exactly the sequence the real dropdowns trigger) produced only a generic
  "Runtime Error" with no diagnostic detail visible from outside the server. Chasing
  that blind became its own open-ended reverse-engineering project rather than a
  bounded fix, so it was abandoned in favour of the option below.
- **Used:** block the page's image/font/stylesheet/media requests outright
  (`page.route()`), since the page only needs to be *readable* by this code — its
  visual rendering was never needed. This directly targets "browser is still busy
  loading something in the background" without needing to know exactly which resource
  was slow. Verified locally: same 5 real December-2025 results still returned
  correctly, and **noticeably faster** (~9 seconds vs ~18 before) — real evidence
  those blocked resources were adding meaningful, avoidable load time.

**Result: the next real GitHub Actions run succeeded completely** — `4 of 4 source(s)
checked successfully`, zero errors, and `baseline captured for egazette-meity: 3
document(s)` in the email. The daily automated eGazette discovery run is now working
end-to-end in production, not just locally.

**A separate, minor, self-resolving issue seen along the way:** on one run, the bot's
own commit-and-push step at the end failed with a `git push` rejection, because
Gautam's own manual `git push` happened to land on `main` at almost the same moment.
This is a plain timing race in the existing (pre-dating this work) commit step, which
doesn't retry on a rejected push. Low-impact when it happens (worst case, the next
day's run just re-baselines a source instead of losing anything — nothing is ever
silently lost, since nothing had been marked `alerted=1` yet), and it self-resolved
the moment the next run tried again. Making that commit step retry
(`pull --rebase` + `push`, a couple of times) instead of failing outright on the first
collision is a reasonable, low-effort follow-up if these races keep happening, but
wasn't done as part of this session since it was never actually blocking.
