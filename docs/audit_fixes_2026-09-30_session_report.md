# Audit fixes, 30 Sep 2026 — full session report

**Branch:** `audit-fixes-2026-09-30` — **not pushed, not merged.** Publishing is
Gautam's decision.
**Tests:** 76 before this work → **176 passing, zero failures.**
**Cost:** **$0** — no AI calls at all. The only network traffic was two polite,
read-only fetches of the MeitY Rules PDF while proving a repair script.
**Spec for the job:** `Claude outputs/AUDIT_REPORT_2026-09-30_opus.md`, an
independent audit of commit `6022d45`.

**Jargon, defined once, because it is the theme of this whole session:**
- A **guard** is a test whose only job is to shout if the legal text stored in
  the database stops matching the official government PDF.
- A **negative test** is a test that deliberately breaks something and then
  *requires* the guard to notice. It matters because **a guard that can never
  fail is not protecting anything — it is decoration.** Two of this project's
  guards turned out to be exactly that.
- A **baseline** is the copy of a web page's text kept from the last time the
  project looked at it, so that today only the *differences* need to be examined.
- A **fingerprint** (or hash) is a short code computed from a document's text.
  Same text, same code; one word different, completely different code. It is how
  the project tells "this page changed" from "this page is the same".

---

## 1. What this session was asked to do, and what it found

The instruction was to carry out Phase 0 and Phase 1 of the audit-fix plan (the
four **critical** findings C-1 to C-4), with a note: *"I think the session got
interrupted. If the work is done then skip this task, or else pick up from where
you left off and complete this task."*

It had been interrupted, but it had got **further** than the pasted instructions.
Reading the repository first showed:

- The four critical fixes were **already written and committed** — six commits,
  `6fbf734` through `19eaaad`.
- Work from two *later* sessions had also been done: the reliability fixes
  (H-1, H-2, H-3, M-2, M-3, M-8, M-13, M-14, L-5) were committed in `19eaaad`,
  and a further batch (H-4, H-6, M-1, M-5, M-6, M-7, M-12, L-3) was sitting
  **uncommitted** in the working tree.
- All 176 tests passed.

So the code was in good shape. What was missing was everything *around* the code
— and one of those gaps was a real defect, not paperwork.

### Why the sessions are all on one branch

`Claude outputs/run_audit_sessions.ps1` was designed to run Sessions 2 and 3 on
their own stacked branches (`audit-fixes-2-reliability`,
`audit-fixes-3-outputs-data`). Those branches do not exist, so **the runner never
ran** — an interactive session did all of the work on `audit-fixes-2026-09-30`
instead. This matters for a practical reason recorded in §7 below.

---

## 2. Verifying the inherited work (not taking the commit messages on trust)

Each of the four critical fixes was checked against the actual code, not against
what its commit message claimed.

| Finding | What was checked | Result |
|---|---|---|
| C-1 | `scripts/rebuild_act_verbatim_2026-09-23.py` — do the checks read `provisions.full_text` from the database? | Yes. Header comment says so, and `check_c1/c2/c4` take the stored text. PDF text is now only the `--apply` payload. |
| C-2 | Is the 97%/90% word-set fallback gone, and replaced with an ordered comparison? | Yes. `ORDERED_RATIO_MIN = 0.995`, `difflib.SequenceMatcher`, word-order gate. `_KNOWN_EXCEPTIONS` holds exact reviewed 4-tuples. `pytest.importorskip` for the PDF libraries. |
| C-3 | Is a baseline written when a source is first recorded, and is a missing-but-should-exist baseline a loud error? | Yes. `fetch_sources.py` writes the snapshot in the same step; `classify_change.py` separates a genuine first sighting (reported as a note in the email) from a data-integrity fault (raises). |
| C-4 | Does an authority table exist, is it enforced in two places, and does it fail closed? | Yes. `may_amend` in `fetch_sources.py`; enforced in `classify_change.classify()` **and** `apply_change.apply()`; an unlisted URL gets an empty list. PIB makes no AI call. eGazette home page retired. TLS pinned via `certs/egazette-chain.pem`. |

---

## 3. Red → green evidence, with its provenance labelled

I inherited these fixes, so I did not watch most of them go red. Being precise
about which evidence is which:

### C-2 — proven live, by re-running the old check

The pre-fix word-set check from commit `6022d45` was reconstructed exactly and
run against the audit's four edits:

| Edit made to the stored law | Old check said | New check |
|---|---|---|
| `six months` → `six years` (Rule 19) | **passed** — 100% word coverage | caught |
| `shall not participate in or vote on` → `may participate in and vote on` (Rule 19) | **passed** — 100% word coverage | caught |
| `shall be` → `may be` inside a 1,650-character Schedule block | **passed** — 99.7% word coverage | caught |
| `shall be` → `may be` (Rule 19) | **passed** — for a different reason, see below | caught |

Three of the four slipped through the word-coverage fallback: it asked only
whether each word appeared *somewhere* in the PDF, ignoring word **order**, and
legal text reuses its own vocabulary heavily.

The fourth passed for a **different and arguably worse reason**: the mutated
fragment occurs in the PDF independently, so it matched *exactly*. Both holes are
closed.

The second row is the one worth remembering: a Board member's
conflict-of-interest ban reversed into a permission, and the guard called it
verbatim.

### C-1 — proven by reading the pre-fix code

At `6022d45`, `run_checks()` begins each row with
`full_text = render_full_text_for_row(pid, row)` — text built **from the PDF** —
and then checks that. The database was used only to compare the *list* of section
IDs. It was comparing the PDF with itself, so it could not fail however badly the
database had drifted.

### C-3 — proven directly against the live committed database

A read-only query of `db/dpdpa.db`:

```
SRC-0001 | MeitY    | .../53450e6e5d...pdf   | hash= 76094c72     <- history, but
SRC-0002 | MeitY    | .../2bf1f0e9f0...pdf   | hash= f15bda1f
SRC-0005 | eGazette | https://egazette.gov.in/ | hash= 31c249b6
SRC-0007 | PIB      | .../RssMain.aspx...    | hash= 48bfd470
snapshots present: SRC-0002, SRC-0005, SRC-0007                   <- ...no baseline
```

SRC-0001 is the DPDP Rules 2025 PDF — the single most important document this
project tracks. It had a fingerprint (so the project had seen it before) and no
stored text to compare against. Exactly the fault C-3 describes.

### C-4 and H-2 — verified from the committed diff and the passing tests

Not by watching them fail.

### H-4 and H-6 — exist and **pass**, rather than failing as designed

Phase 0 asked for these as failing tests first. They pass, because the
interrupted session's later work had already fixed the underlying problems. That
work is commit `4e445cf`.

---

## 4. What I added this session

### 4a. Two repair scripts that the code already told you to run, but which did not exist

Three places in the committed code named a one-off script by name:
`classify_change.py:529`, `fetch_sources.py:175`, `export_excel.py:241`. Neither
script existed.

**One of these was a real defect, not a documentation slip.** With C-3's fix in
place, the next time MeitY publishes an amended Rules PDF, the pipeline correctly
refuses to carry on and raises an error telling Gautam to run
`scripts/backfill_source_snapshots_2026-09-30.py`. That file was not there. The
instruction would have arrived at exactly the moment production broke, and been
impossible to follow.

**`scripts/backfill_source_snapshots_2026-09-30.py`** — creates the missing
SRC-0001 baseline. Its important property is that **it refuses to guess**. It
fetches the document and compares the fingerprint with the one already recorded:

- *Fingerprints match* → the document has not changed since the project last
  looked, so today's text genuinely is the missing baseline. Safe to store.
- *Fingerprints differ* → the document **has** changed and nobody has examined
  that change. Storing today's text as "what it looked like before" would bury
  the change permanently — which is the very bug this script exists to repair.
  It stops, says so plainly, and says what to do instead.

Proven on a throwaway copy, both ways:

```
safe case      : fetched 120,816 characters, fingerprint 76094c7228c8...
                 MATCHES the recorded fingerprint -> baseline written, exit code 0
tampered case  : recorded deadbeef7609..., fetched 76094c7228c8...
                 REFUSED, nothing written, exit code 1
```

The non-zero exit code matters: a refusal reaches a shell or a scheduled job as a
real failure, instead of looking like success.

**`scripts/mark_unwatched_sources_2026-09-30.py`** — marks the four leftover
`source_log` rows `watched = 0`, so the Excel tracker's Source_Log sheet finally
matches its own description ("what is being watched right now"). The four are
SRC-0003 and SRC-0006 (one-off Gazette/MeitY PDFs fetched by hand in an earlier
audit), SRC-0004 (PIB's old HTML page, replaced by the RSS feed) and SRC-0005
(the retired eGazette home page). **Nothing is deleted** — those rows carry
`linked_change_ids`, the record of which change came from where.

Proven on a throwaway copy, including the checks the hard rules require:

```
row counts  real: {provisions: 79, change_log: 142, source_log: 7}
row counts  copy: {provisions: 79, change_log: 142, source_log: 7}
provisions identical (text / status / latest_change_id): True
watched flags: SRC-0001:1 SRC-0002:1 SRC-0003:0 SRC-0004:0 SRC-0005:0 SRC-0006:0 SRC-0007:1
second run   : "Nothing to do" — safe to run twice
```

Both scripts default to a dry run, take `--db` so they can be rehearsed on a
copy, call `init_schema()` so an older database gains the `watched` column
additively (every existing row keeps the default `1`), and read their work back
afterwards rather than trusting that the write succeeded. **Neither was run
against `db/dpdpa.db`.**

### 4b. Five negative tests for a hole I went looking for and did not find

A `_KNOWN_EXCEPTIONS` entry records a reviewed, documented difference between the
stored text and the PDF. The risk worth checking: does an exception shelter only
its own exact text, or does it quietly excuse the **whole provision** it is
listed under? Seven of the eight provisions carrying an exception are Schedules,
so if it were the latter, those Schedules would be unguarded legal text while
the test suite still reported all green.

I mutated four excepted provisions somewhere **other** than the excepted phrase
— including another clause of the very same Seventh Schedule table row:

```
DPDPR-SCH7  "disclosure of any information"   -> caught
DPDPR-SCH7  "sovereignty and integrity of India" -> caught
DPDPR-SCH5  "four lakh fifty thousand"        -> caught
DPDPR-SCH6  "Travelling allowance"            -> caught
DPDPR-SCH4  "clinical establishment"          -> caught
```

**C-2 is not hollow.** The exception mechanism is a targeted substitution — it
swaps the known-different string for the PDF's version and then still requires
the whole passage to match — so it is narrow by construction. That is now a
permanent test (`test_an_exception_does_not_shelter_the_rest_of_its_provision`)
rather than an assurance in a report.

### 4c. Documentation that had become untrue

`README.md` — four claims corrected:

1. "Three sources, **in trust order**" listed **PIB first**. Backwards: PIB is
   alert-only and may change nothing. Rewritten so the two MeitY PDFs come first
   as the only sources permitted to change stored legal text, with PIB described
   in the audit's own words as a **"coincidence detector, not a reliable
   source"**.
2. The eGazette home page was still described as a fetched source that "hashes
   the home page as a coarse best-effort signal". It was retired on 30 Sep 2026.
3. "Also required disabling TLS verification specifically for this host" — no
   longer true; the chain is pinned in `certs/egazette-chain.pem`.
4. "Not yet built" still described the retired home-page hash as current.

Also newly written down, because none of it was recorded anywhere:

- The **source-authority rule** and its table (the headline C-4 fix had no README
  entry at all).
- **Court orders and Data Protection Board orders are watched by nothing**, and
  no code was added to watch them.
- **`confidence_score` is recorded but deliberately does not gate** anything.
- The **Excel README sheet is stale** on two points, and why it is corrected on
  `main` rather than here.
- The architecture diagram, the file-layout list and the auto-apply section were
  each corrected where they still described the old source set or implied nobody
  had reviewed anything (79 provisions and 142 change rows were reviewed by hand
  on 29 Sep 2026).

`CHANGELOG.md` and `platform/CHECKPOINT.md` had **no entry for any of this
work** — a direct miss against the standing logging rule. Both now have one.

### 4d. A correction to my own work

I first wrote in the checkpoint that this work "fixes the 32 PDF-extraction test
failures" noted on 29 September. I never reproduced those 32 failures, so that
was an assertion about production history that nobody had checked — exactly what
this project's rules exist to prevent. Commit `8429c60` softens it to what is
actually known: the test file now skips loudly when the PDF-reading libraries are
missing, which is the most likely cause, and that is a reasonable expectation
rather than a verified fact.

---

## 5. Commits on this branch

Oldest first. The first six were inherited; the last three are this session.

| Commit | What it does |
|---|---|
| `6fbf734` | Make the two verbatim guards able to fail (C-1, C-2) |
| `1a93bee` | Give every source a baseline, and stop unauthorised sources writing law (C-3, C-4) |
| `a5d87ec` | Check e-Gazette's certificate properly instead of switching the check off (C-4, TLS) |
| `985cf1d` | Never rewrite line endings in `.pem` files |
| `dedd6c3` | Close a word-boundary hole in the verbatim guard, and test the fallback |
| `19eaaad` | Make it obvious when the pipeline breaks (H-1, H-2, H-3, M-2, M-3, M-8, M-13, M-14, L-5) |
| **`41a4784`** | **Write the two repair scripts, prove the exceptions are narrow, and correct the docs (C-1..C-4)** |
| **`4e445cf`** | **Fix the outputs and the discovery window (H-4, H-6, M-1, M-5, M-6, M-7, M-12, L-3) — see the warning in §7** |
| **`8429c60`** | **Do not claim the 32 test failures are fixed without having checked** |

33 files changed, 5,136 insertions, 490 deletions against `main`.

**Hard rules observed, each checked rather than assumed:**
- `git diff --name-only main...HEAD -- db/dpdpa.db docs/ data/` → empty. No
  bot-owned database, Word or Excel file was touched on this branch.
- `git ls-remote --heads origin "audit-fixes*"` → empty. Nothing was pushed.
- No merge, no force, no history rewrite. Working tree clean.
- The two data scripts were run only against throwaway copies under `var/`
  (git-ignored), which were deleted afterwards.

---

## 6. Test results

```
176 passed, 1 warning
```

Baseline before the audit-fix work was 76. The one warning is a
`CryptographyDeprecationWarning` from `tests/test_egazette_chain.py`: a
certificate in the real e-Gazette chain has a serial number that is not
positive, which a future release of the `cryptography` library will reject. It is
the government's certificate, not our code, and it is worth knowing about before
that library upgrade lands.

Test files, for orientation:

| File | Covers |
|---|---|
| `test_legal_text_verbatim.py` | C-1, C-2 — the verbatim guards and every negative test |
| `test_source_authority.py` | C-4 — the authority table, refusals, forged-notice scenario |
| `test_pipeline_failures.py` | C-3, H-2 — baselines, rollback so tomorrow retries |
| `test_run_reliability.py`, `test_error_noise.py` | the reliability batch |
| `test_egazette_chain.py` | the pinned certificate |
| `test_outputs_and_discovery.py` | H-4, H-6, M-1, M-5, M-6, M-7, M-12, L-3 |

---

## 7. Three things to know before publishing

**1. Do not run `run_audit_sessions.ps1`.** It expects to *create*
`audit-fixes-2-reliability` and `audit-fixes-3-outputs-data` and refuses to
overwrite them — but Sessions 2 and 3 have already been done, on this single
branch rather than on those stacked branches. Running it would re-run both
sessions on top of work that already contains them. All nine commits are on
`audit-fixes-2026-09-30`, so **one merge brings in everything**.

**2. Commit `4e445cf` is work in progress that I did not verify.** It is the
interrupted session's later output. Its 25 tests pass and it reads as finished,
but I did not check it line-by-line against
`Claude outputs/CLAUDE_CODE_PROMPT_audit_fixes_SESSION3_outputs_and_data.md`.
I committed it **separately and labelled** so that it is not lost and can be
reviewed on its own. Read that commit before merging.

**3. The approval gate was deliberately not built.** It is Gautam's and EY's
decision. The three options, in one line each: **(A)** every AI-detected change
waits in a queue until a person approves it — safest, but the tracker stops being
self-updating and somebody must check the queue daily or it silently rots;
**(B)** only changes to *legal text* wait, while summaries and metadata apply
automatically — a middle path, more code to write; **(C)** keep auto-apply but
add a daily digest that a person signs off *after* the fact — cheapest and
closest to today's behaviour. Auto-apply is unchanged apart from the C-4
restrictions.

---

## 8. What only Gautam does, in this order

1. Review the diff — especially `4e445cf` — then merge `audit-fixes-2026-09-30`
   into `main` and push.
2. Run the daily workflow once from the GitHub Actions tab and confirm it is
   green.
3. `python scripts/mark_unwatched_sources_2026-09-30.py --apply` — no internet
   needed. Rehearse with no flags first; it is a dry run by default.
4. `python scripts/backfill_source_snapshots_2026-09-30.py --apply` — needs the
   internet. If it **refuses**, the Rules PDF has changed since the last
   recorded fetch and wants a human look; the message says what to do.
5. Regenerate the Excel tracker on `main` (never on a working branch) so the
   Source_Log sheet matches the database.

---

## 9. Deliberately not done, and why

| Item | Decision |
|---|---|
| Approval gate (audit §7 options A/B/C) | Not built. Gautam's and EY's call — see §7.3. |
| `confidence_score` threshold (M-10) | Not added. The audit measured a **genuine** amendment at 0.65, so a gate would block real changes. Confidence is recorded but does not gate; now stated in the README. |
| Rename `DPDPR-SDF-R13` (L-2) | Not done. Renaming a primary key touches bookmarks, change history and tests. Recorded as a follow-up. |
| `topic_category` (L-9), `sort_order` (L-1), Sub-Rule / Board Order schema values (L-4) | Untouched beyond a README note, as instructed. |
| Court orders and Board orders (S11 / S12) | Out of scope for code. Now named in the README's known limitations so nobody assumes they are watched. |
| Excel README sheet wording | Left alone deliberately. `data/*.xlsx` is owned by the daily bot and must not be changed on a working branch; recorded in the README as a known limitation to fix on `main`. |
| MeitY's own document-listing pages | Still blocked (HTTP 403). Not worked around — the project forbids it. |

---

## 10. Cost

**$0.** Every test uses the mock classifier. The only network traffic in the
whole session was two polite, read-only fetches of the MeitY Rules PDF while
proving the backfill script, using the existing truthful User-Agent. No CAPTCHA,
login, block or rate limit was touched. No secret was printed, logged or
committed.
