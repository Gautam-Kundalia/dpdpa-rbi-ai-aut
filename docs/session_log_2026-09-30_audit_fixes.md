# Session log — audit fixes, 30 September 2026

Everything that happened today, in the order it happened, on branch
**`audit-fixes-2026-09-30`**. **Nothing was pushed. Nothing was merged. `main`
was never touched.**

This file exists so that somebody who was not here can reconstruct the day
without reading three other documents. It is deliberately blunt about which
claims were *checked* and which were *inherited*.

**Related reading:**
- `docs/audit_fixes_2026-09-30.md` — every audit finding, one row each, with its
  status and the test that proves it. **Start here if you want the score.**
- `docs/audit_fixes_2026-09-30_session_report.md` — the narrative of the first
  part of the day.
- `CHANGELOG.md` — the plain-language entries.
- `Claude outputs/AUDIT_REPORT_2026-09-30_opus.md` — the audit itself.

---

## The day in one paragraph

An independent audit of commit `6022d45` raised 4 Critical, 7 High, 14 Medium
and 9 Low findings. Three working sessions on one branch closed all of the
Critical and all of the High findings — nine in code, two as one-off scripts
Gautam runs — plus most of the Medium and Low ones. The last session's job was
**not** to write new features: it was to check, line by line, a commit that the
session before it had explicitly flagged as unverified work in progress. That
check found one real break that would have hit Gautam on his first attempt, and
one test that could not fail. Both were fixed before anything else was built.

---

## The commits, oldest first

Times are local (IST). Test counts are the full suite (`python -m pytest`) at
that point.

| # | Time | Commit | What it did | Tests after |
|---|---|---|---|---|
| 1 | 09:09 | `6fbf734` | Make the two verbatim guards able to fail (C-1, C-2) | — |
| 2 | 09:20 | `1a93bee` | Give every source a baseline; stop unauthorised sources writing law (C-3, C-4) | — |
| 3 | 09:29 | `a5d87ec` | Pin e-Gazette's certificate instead of switching TLS checking off (C-4) | — |
| 4 | 09:29 | `985cf1d` | Never rewrite line endings in `.pem` files | — |
| 5 | 09:32 | `dedd6c3` | Close a word-boundary hole in the verbatim guard; test the fallback | — |
| 6 | 09:49 | `19eaaad` | Make it obvious when the pipeline breaks (H-1, H-2, H-3, M-2, M-3, M-8, M-13, M-14, L-5) | — |
| 7 | 18:57 | `41a4784` | Write the two repair scripts the code already named but which did not exist; prove the verbatim exceptions are narrow; correct the README (C-1..C-4) | 176 |
| 8 | 18:57 | `4e445cf` | Fix the outputs and the discovery window (H-4, H-6, M-1, M-5, M-6, M-7, M-12, L-3) — **committed as unverified work in progress, and labelled as such** | 176 |
| 9 | 18:59 | `8429c60` | Withdraw an unchecked claim that this work fixed the 32 PDF-extraction test failures | 176 |
| 10 | 19:13 | `154a659` | Write `docs/audit_fixes_2026-09-30_session_report.md` | 176 |
| 11 | 20:17 | `c3828c6` | **Fix what checking `4e445cf` found**: the Excel rebuild crashed, and the M-5 test could not fail | **178** |
| 12 | 20:35 | `4e42aa0` | Write the two data-repair scripts (H-5, H-7, M-11) and their tests | **198** |
| 13 | 20:40 | `b1e8cf4` | Correct the documentation the audit proved wrong; write the finding-by-finding table (L-7, Task C) | 198 |
| 14 | — | this commit | CHANGELOG, CLAUDE.md standing rules, checkpoint, this file | 198 |

Baseline before any of this work: **76 tests.** Final: **198, zero failures.**
The single warning in the run is a `CryptographyDeprecationWarning` about a
non-positive serial number in the real e-Gazette certificate chain — the
government's certificate, not this project's code, and worth knowing about
before the `cryptography` library is next upgraded.

---

## Session 3B, in detail — what was checked, and how

The session before this one committed `4e445cf` with a warning in its own
message: *"I have not checked it line-by-line against its session prompt, so
treat the finding coverage below as the code's own claim rather than as
verified-complete."* That is the honest thing to do, and it left a real job.

### Method

Two throwaway `git worktree` checkouts under the session scratchpad — one at
`main`, one at the branch head. Nothing in the real working tree was ever
dirtied, so the rule about never touching `db/dpdpa.db`, `docs/*.docx` or
`data/*.xlsx` held by construction rather than by care.

For each claimed fix: put the **old** behaviour back in the branch worktree,
run the test that is supposed to cover it, and require it to go **red**. A fix
whose test stays green when the fix is removed is not covered.

### Results

| Item | Verdict | Evidence |
|---|---|---|
| **3a — H-4**, Excel links relative to the workbook | **Verified** | Restoring `str(PROJECT_ROOT / val)` turns 2 tests red, including the audit's exact check (no target starts with `/` or a drive letter) |
| **3b — H-6 + M-1**, every government amendment shown | **Verified** | Restoring `main`'s `latest_change_id` query turns 3 tests red. All qualifying changes returned; each highlighted at every occurrence; caption lists every change; Excel adds "(+N earlier)"; the docstring is corrected |
| **3b — acceptance test** | **Verified, re-derived from scratch** | See below |
| **3d — M-5**, `watched` column and Source_Log | **PROBLEM — fixed now** | Two faults; see below |
| **3e — M-6**, page-count cross-check | **Verified** | Removing the check turns `test_a_month_whose_count_disagrees_is_a_loud_failure` red |
| **3e — M-7**, one bad Gazette ID | **Verified** | Making a bad ID raise again turns `test_a_bad_gazette_id_keeps_the_good_rows` red; the bad row reaches both the warnings list and the run's error list |
| **3e — M-12**, catch-up window | **Verified** | Fixing the window at two months turns 2 tests red; widening after 25 days, capped at 12 months, always reported |
| **3f — L-3**, `In_Force` robust to locale | **Verified** | Removing `IFERROR` turns its test red |
| **3c — L-8**, provenance and disclaimer | **Verified (already done)** | Blanking `provenance_lines()` turns 3 tests red; both documents carry all four lines, the Rules document names G.S.R. 892(E) |
| **3f — L-5**, unknown attachment type | **Verified (already done)** | Restoring `MIME_TYPES[...]` turns its test red |
| **3f — L-7**, the PyMuPDF note in `CLAUDE.md` | **Checked, then fixed** | `import pymupdf` and `import fitz` both succeed on this PC, PyMuPDF **1.28.2** (`fitz` prints a deprecation warning). The note was outdated. Corrected |
| **4d — `mark_unwatched_sources`** | **Verified** | Dry-run by default, `--apply`, prints before/after, safe twice, deletes nothing; now covered by tests on a throwaway copy |

### The two problems in `4e445cf`, and what they were

**1. `python src/export_excel.py` crashed on the committed database.**

```
sqlite3.OperationalError: no such column: watched
```

`4e445cf` taught the exporter to read `source_log.watched`. That column is added
by an additive migration — but only `run_pipeline.py` ever applied it. The
committed `db/dpdpa.db` does not have the column. Rebuilding the tracker by hand
is exactly what the hand-over instructions ask Gautam to do, and it is usually
the *first* thing anyone runs after pulling new code, so it would have failed on
his first attempt, on `main`. Fixed by calling `init_schema()` first, like every
other entry point does. It is additive and idempotent: it adds only what is
missing and changes no existing row.

**2. The test for that column could not fail.**

It ran its own `SELECT ... WHERE watched = 1` and then asserted on that result —
so it was checking its own query, not the exporter's. Deleting the filter from
`export_excel.py` left **all 176 tests green**. Replaced with one that builds the
workbook through `export_excel.main()` and reads the Source_Log sheet back out
of it. Also added the old-schema upgrade test the project's own hard rule 9
requires, which nothing covered: a database with no `watched` column gains it,
every existing row keeps its values and defaults to still-watched, and the
tracker rebuilds on it.

Both new tests were shown failing against `4e445cf`'s code before the fix.

This is worth recording for its own sake: the audit's headline finding (C-1) was
a guard that could not fail, and within the same day the same shape of mistake
had recurred in a new test. It is not a rare mistake. It is the default outcome
unless somebody deliberately breaks the code and watches.

### The acceptance test, re-derived rather than taken on trust

The plan required that, for today's committed database, the regenerated
documents and workbook be identical in text and highlighting to what `main`'s
code produces. That was checked by regenerating from the same committed database
in both worktrees and comparing run by run and cell by cell.

**Word documents — body text identical, highlighting identical:**

```
DPDP_Rules_2025.docx
  main   : 4 YELLOW ['in the Official Gazette' x2, 'Departments', 'order']
           3 STRIKE ['of this Gazette' x2, 'Department']
           3 CAPTIONS (CHG-0086, CHG-0087, CHG-0088)
  branch : identical
DPDP_Act_2023.docx
  main   : 0 highlights      branch : 0 highlights
```

The only text difference is the L-8 provenance block that was asked for.

**Workbook — 158 differing cells, every one of them intended:**

```
Master_Provisions : 79 hyperlink targets  (absolute path -> ../docs/...#ANCHOR)   [H-4]
                    79 In_Force formulas   (DATEVALUE -> IFERROR(DATEVALUE))       [L-3]
Change_Log        : 0 differing cells      yellow rows: CHG-0086/87/88 in both
Source_Log        : 0 differing cells      (all rows default to watched = 1)
README sheet      : 8 cells — the corrected wording
Last_Regulatory_Change : identical in both
```

These figures match the audit's own §3 measurements exactly.

---

## The data scripts, proven on throwaway copies

**None of these was run against `db/dpdpa.db`.** Each was rehearsed with `--db`
pointing at a copy under the session scratchpad.

| Script | Finding | What it does | Proven |
|---|---|---|---|
| `mark_unwatched_sources_2026-09-30.py` | M-5 | marks SRC-0003/4/5/6 `watched = 0`; deletes nothing | dry run changes nothing; `--apply` retires exactly 4; safe twice |
| `restore_verbatim_wording_2026-09-30.py` | H-7, M-11 | restores the Seventh Schedule's real wording and 15 heading dashes, as `data_correction` | as above; and the verbatim guard then accepts all three provisions **with their exceptions removed** |
| `fix_corrigendum_schedules_2026-09-30.py` | H-5 | records corrigendum items (iv) and (v) as 4 `regulatory` rows | as above; `provisions` untouched; CHG-0089/0091 untouched |

All three were then run together, in the order Gautam will run them, and the
documents regenerated from the result. **Exactly** the expected things changed:
4 new yellow Excel Change_Log rows; First and Fourth Schedules appearing in
`Last_Regulatory_Change` with "(+1 earlier)"; 3 new Word highlights and 2 new
captions; the restored Seventh Schedule wording; the 15 heading dashes; only the
3 watched sources in Source_Log; provenance lines on both documents. Nothing
else moved.

### Three things found while doing it that were not in the plan

1. **`(18 of 2013)` appears three times in the First Schedule**, and only one is
   the one the corrigendum corrected. The context that makes each pair unique is
   therefore taken from the official PDF — which still prints the *uncorrected*
   wording, and prints it exactly once — rather than from the corrected text,
   which cannot tell the three apart. A first attempt that derived the
   pre-corrigendum text by reversing the correction everywhere picked the wrong
   occurrence; caught before it went anywhere.
2. **Corrigendum item (v)(b) is not a phrase swap.** The original Gazette
   printed the Fourth Schedule Note's items as (a), (a), (b)…(f) — two of them
   labelled (a) — and the corrigendum relabels the whole list (a) to (g). It is
   recorded as the run of text that actually changed. Because that run spans
   several paragraphs and the renderer only highlights text it finds whole
   inside one paragraph, this one is **captioned but not highlighted**, with a
   warning on stderr. That is a deliberate trade: a complete audit trail over a
   prettier document.
3. **The 15 heading dashes were never load-bearing for the verbatim guard.**
   Removing their exceptions and testing the *unfixed* text showed it still
   passes, because the guard deliberately ignores punctuation. The Seventh
   Schedule's exception, by contrast, **is** load-bearing: remove it and the
   unfixed text fails, correctly. So restoring the dashes matters for the
   faithfulness of documents that reach a reader, not for the guard — and saying
   so is more useful than implying the guard was blind.

Two exceptions remain after the fix: the Fifth Schedule prints `namely:-` in two
places where the database has `namely:`. Outside this session's stated scope
(15 headings), so named in the README as a follow-up rather than quietly widened
into.

---

## Mutation spot-check

Five deliberate corruptions of the stored law, each on a throwaway copy, each
required to be caught by the project's own guards.

```
Rules DPDPR-R19  'shall be' -> 'may be'                    CAUGHT
Rules DPDPR-R19  'six months' -> 'six years'               CAUGHT
Rules DPDPR-R19  conflict-of-interest ban -> permission    CAUGHT
Act   DPDPA-S33  replaced with nonsense                    CAUGHT (exit 1)
Act   DPDPA-S33  'significant' -> 'insignificant'          CAUGHT (exit 1)
```

Every one of the first three **passed** the pre-audit guard. The third is the
one to remember: a Board member's conflict-of-interest ban reversed into a
permission, and the guard called it verbatim.

Separately, and already covered by permanent tests: a forged amendment from the
retired e-Gazette home page is refused; a forged PIB item never reaches the model
at all; and an `apply()` that raises leaves the fingerprint **and** the baseline
untouched, so the next day sees the change again instead of losing it.

---

## Hard rules, checked rather than assumed

- `git status` clean; `git diff --name-only main...HEAD -- db/dpdpa.db docs/ data/`
  returns nothing. No bot-owned database, Word or Excel file was changed.
- Nothing pushed, nothing merged, no force, no history rewritten.
- Every data script run against a copy, never `db/dpdpa.db`.
- **$0 spent. No AI calls. No network requests at all this session.**
- No secret or `.env` value was printed, logged or committed.

---

## What is still open, and who owns it

**Gautam:**
1. Review the diff and merge the branch into `main`.
2. **Approve the four corrigendum phrase pairs (H-5) and the Seventh Schedule
   wording (H-7)** — the scripts print them and stay dry runs until he does.
3. Create the healthchecks.io check and add the `HEARTBEAT_URL` secret (H-1),
   then confirm both workflows go green on GitHub.
4. At a quiet time — **not around 06:00 IST** — run the data scripts, regenerate,
   and commit.
5. Revoke the old OpenRouter key, **then** delete its two lines from `.env` (M-9).

**Gautam and EY together:**
6. The approval gate — options A, B and C. The audit recommends **C**. Not built,
   deliberately.

**Nobody has to do soon:** audit L-1, L-2, L-4, L-9; the two remaining Fifth
Schedule run-in dashes; teaching the discovery step's headless browser to use
`certs/egazette-chain.pem` so the last `ignore_https_errors=True` can go; the
"apply new documents oldest-first" engine.

---

## One warning carried forward

**Do not run `Claude outputs/run_audit_sessions.ps1`.** It expects to *create*
`audit-fixes-2-reliability` and `audit-fixes-3-outputs-data` and re-run Sessions
2 and 3 on them. Those sessions were done on this single branch instead, so
running it would re-run work that already exists. All fourteen commits are on
`audit-fixes-2026-09-30`: **one merge brings in everything.**
