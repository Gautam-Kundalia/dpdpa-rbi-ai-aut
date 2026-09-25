# Changelog

## 2026-09-22 → 2026-09-23 — Silent-failure fixes + Claude migration (commit `fbd1c4e`)

Follow-up to a real-data audit (see `pipeline-architecture-flow.html` / the
project walkthrough doc) that found the pipeline could fail without anyone
knowing. This session fixed what could be proven safe overnight and left one
issue open, documented, and failing loudly instead of silently.

### Fixed (real-data tested before commit)

- **`src/classify_change.py` — Bug A, silent classification failure.**
  Previously, if every retry of the AI call failed, the code caught the
  exception, marked `source_log.processing_status = 'Error'`, and returned
  `[]` — indistinguishable from "AI found nothing." `run_pipeline.py` then
  saw no exception, `errors[]` stayed empty, and GitHub Actions showed green
  on a genuinely broken day. Fixed: after `MAX_CLASSIFY_ATTEMPTS` (raised
  2 → 3), the function now raises `ClassificationFailed` instead of
  returning `[]`. Proven with a forced failure (invalid model name → real
  400 → raised → exit 1) and with real, unplanned production failures
  (a 200-OK-wrapped OpenRouter/Nvidia 503, a malformed-JSON response, a
  JSON syntax error) — all surfaced correctly instead of being swallowed.

- **`src/run_pipeline.py` — Bug B, `source_log` stuck on `New`.**
  When `classify()` legitimately found no change, no terminal status was
  ever set, so the row stayed on `New` forever — indistinguishable from
  "never checked." Fixed: a legitimate empty result now updates the row to
  `No Change Detected`. Proven with a real PIB run.

- **`src/notify.py` — misleading email subject line.**
  The subject was keyed only on `len(applied_changes)`, so it read "No
  changes detected today" even on a run with real errors (the body listed
  them, but the subject didn't). Fixed: the subject now reflects error
  count first, so a problem can't be missed by skimming an inbox.

- **`src/classify_change.py` — OpenRouter 200-wrapped-error bug.**
  Root cause: OpenRouter can return HTTP 200 with an `{"error": ...}` body
  when the upstream provider (Nvidia free tier) is overloaded, which
  `resp.raise_for_status()` cannot catch. Fixed: response body is now
  checked for an `"error"` key and raised as a real `RuntimeError` with the
  upstream message, instead of dying later with a bare `KeyError: 'choices'`.
  Also: `raise_for_status()` failures now include the response body
  (`resp.text[:500]`) in the raised error, so future failures are
  diagnosable from the email alone.

- **`src/classify_change.py` — migrated 3 of 4 sources to Anthropic Claude.**
  Rules PDF, PIB, and eGazette now call Claude Haiku 4.5 with forced
  tool-use (`tool_choice: {"type": "tool", "name": "report_changes"}`)
  instead of OpenRouter's free-tier model with loose JSON prompting — this
  guarantees schema-conformant output instead of hoping the model follows
  instructions. All three tested clean against live government pages.
  Also added `_relevant_provisions()`: since a source's URL identifies
  whether it's about the Rules or the Act, the "current provisions" dump
  sent to the model is now filtered to just that instrument's provisions
  instead of always sending all 79 (Rules prompt −35.3%, Act prompt
  −29.1%). Sources that could reference either instrument (PIB, eGazette)
  still get the full set.

### Known issue — not fixed, left failing loudly on purpose

- **Act PDF classification fails every time, under both providers.**
  Under Claude, it hits `stop_reason: max_tokens` with the tool call's
  `input` coming back empty, even after `max_tokens` was raised 4096 →
  16000 as a diagnostic. This is not a regression — it was already failing
  under OpenRouter (wrong-shaped JSON) — but it's now failing *visibly*
  (`ClassificationFailed` → real error email) instead of silently.
  Working theory, not yet confirmed: this likely connects to a known,
  separate problem — the original audit found 3 of 5 spot-checked Act
  sections in the database don't exactly match the official government
  PDF. If that mismatch rate holds across more of the 48 relevant Act
  provisions, the model may be trying to report an unusually large number
  of real differences in one call and running out of output budget before
  it can finish, rather than this being a pipeline logic bug.
  **Deliberately deferred to a dedicated follow-up** rather than guessing
  further tonight: (1) a cheap diagnostic capturing the raw partial output
  of a repeat Act-PDF call to confirm/deny the theory, (2) a full,
  provision-by-provision re-diff and correction of the Act table against
  the official PDF (only 5 of 48 were originally spot-checked), (3)
  re-testing Act PDF classification after that correction.

### Also flagged, lower priority, not touched this session

- Rules PDF has 3 wording defects in the exact tracked government PDF
  (Rule 23(1), Rule 13(5), Rule 1(2) vs 1(3)/(4)); a possible corrigendum
  (G.S.R. 892(E), 10 Dec 2025) is unconfirmed against a primary source.
- Daily GitHub Actions run consistently fires ~4.5–5 hours late vs. its
  00:30 UTC schedule — suspected Actions scheduler queuing, unconfirmed.
- The three staged commencement dates (13 Nov 2025 / 13 Nov 2026 / 13 May
  2027) may need to be 14 Nov — unconfirmed against a primary Gazette copy.

### Cost

~$0.51 of Anthropic API credit spent proving these fixes against real data
tonight (out of ~$4 available).

## 2026-09-23 — Act PDF follow-up: theory refuted, real data-quality problem confirmed, NOT fixed (no commit)

Follow-up session dedicated to the Act PDF's `max_tokens` failure documented
above. Result: the leading theory is refuted, a real and more serious
data-quality problem was confirmed and documented, but no code or DB change
was made — this entry is a report, not a fix.

### Step 1 — diagnostic (real Anthropic API, real Act PDF)

Ran a standalone streaming diagnostic against the live Anthropic API using
production's exact prompt/tool/model setup, capturing partial tool-call JSON
even under `stop_reason: max_tokens`. Cross-checked at the raw SSE wire level
(bypassing the SDK's stream helper entirely) to rule out a client-side
accumulation bug. **Finding: the model consumes its entire 4096-token output
budget while emitting essentially zero visible tool-call content** — one
`content_block_start`, one empty `input_json_delta`, then immediate
`stop_reason: max_tokens`, confirmed identical at the raw SSE frame level.
This **refutes** the working theory ("model is mid-writing many legitimate
diffs and runs out of room") — there is no partial JSON ever building up.
Root cause of the `max_tokens` failure itself remains open.

Cost discipline note: the task asked for 1-2 diagnostic runs (~$0.20 budget);
this took 6 runs total (4 iterations to get the SDK's streaming event
handling right, plus a failed-then-fixed raw-SSE attempt) at ~$0.05 each,
~$0.30 total — over the soft guidance but nowhere near the $2.00 hard cap.

### Step 2 — mechanical Act-table audit (docs/act_table_audit_2026-09-23.md, ~$0, no AI calls)

Re-diffed all 48 `DPDPA-*` DB rows against a freshly downloaded copy of the
tracked Act PDF using pure Python (pypdf + difflib) — no LLM cost. Full
write-up: `docs/act_table_audit_2026-09-23.md`.

Confirms the DB's Act text is not merely "5 sections had transcription
typos" (the prior spot-check's framing) but is largely a **condensed
paraphrase** of the Act (illustrations/explanations dropped, by design —
`DPDPA-S2`'s own text says so), and — more seriously — **at least six rows
contain confirmed substantive errors** verified by direct comparison against
the live PDF text, not just a low similarity score:

- `DPDPA-S26`: uses "Benches" and a (1)/(2)/(3)-with-proviso structure that
  isn't Act language at all (zero matches for "Bench" in a full-text search
  of the fresh PDF; the Act structures this section as three lettered
  clauses instead).
- `DPDPA-S7`: ground (b)(ii) for State processing is a different legal test
  in the DB than in the Act.
- `DPDPA-S17`: exemption sub-sections (1), (3)-(5) omit/conflate real Act
  provisions, understating which obligations a Data Fiduciary is exempt from.
- `DPDPA-S28`: invents a "show cause" notice step and an Indian Evidence Act
  1872 §123/124 citation that aren't in the Act's actual Section 28.
- `DPDPA-S42`: describes a flat ₹250 crore aggregate penalty cap; the Act
  actually caps amendments at *double* the original per-penalty amount —
  different rules with different legal effect. Clearest single finding.
- `DPDPA-S44.1_3` / `DPDPA-S44.2`: confirms and generalizes the prior
  spot-check's "'substituted' vs 'inserted'" defect — it recurs, and the DB
  also drops a reference to the Airports Economic Regulatory Authority Act.

`DPDPA-SCHED` (the penalty Schedule table), by contrast, was verified
**correct** — the mechanical audit's 0.0 similarity score for it was a
tooling false alarm (the Schedule isn't a numbered "Section," so no PDF
counterpart was located; manually re-pairing the PDF's column-extracted
table confirms all 7 penalty amounts match).

A provenance check was attempted: `seed_dpdp_act_full.py` lists
`docs/DPDP_Act_2023.docx` as each provision's source file. That DOCX turned
out to be an export/mirror of this same database (it matches the DB's exact
wording, including this tracker's own "Status: Active" / "Note: Currently
in force" annotations) — not an independent verbatim copy of the Act — so
it cannot corroborate or rule out any theory of where the wrong wording
originated. Provenance of the confirmed errors is unknown; an earlier
version of this entry speculated about an earlier draft Bill without
checking one, and that speculation has been removed as unsupported.

### Steps 3-5 — deliberately not attempted

Per the task's own instruction ("if ANY section's correct reading is
ambiguous... do NOT guess"): six confirmed errors of unknown provenance,
found in a single session with no second human legal reviewer, means
applying corrections from this mechanical pass risks introducing new errors
while fixing old ones. **No writes were made to `db/dpdpa.db`.**
Classification was not re-tested against the Act PDF (Step 4) and the
full-pipeline regression check (Step 5) was not run, since there is nothing
yet to regression-test.

### Cost

~$0.30 total tonight (diagnostics only; Step 2 was $0). Cumulative across
both sessions: ~$0.81 of ~$4 available.

### Not pushed

This entry, `docs/act_table_audit_2026-09-23.md`, and pre-existing
uncommitted changes (`pipeline-architecture-flow.html`, and this file itself
— both already uncommitted at the start of this session, unrelated to
tonight's work) remain uncommitted, pending direction. Recommended next
step: a human legal review of the Act table (starting with the six
confirmed rows above) before any DB correction is attempted, and separately,
further investigation into why the Act PDF classifier call empties its
output budget with no visible content (independent of the data-quality
finding here) — starting with a free, no-API-cost fix: `SYSTEM_PROMPT` in
`classify_change.py` still ends with an OpenRouter-era "respond with ONLY a
JSON object... no markdown fences" instruction that contradicts forced
`tool_choice` (there's no place for "a JSON object" outside the tool
input). Not proven to be the cause (Rules/PIB/eGazette carry the same text
and work), but worth stripping before the next diagnostic spend.

## 2026-09-23 — Candidate `max_tokens` fix tried and ruled out (no commit)

Removed the leftover OpenRouter-era "Respond with ONLY a JSON object... No
prose, no markdown fences" block from `classify_change.py`'s `SYSTEM_PROMPT`
(the candidate flagged in the entry above) — the rest of the prompt was left
untouched, since the "return an empty changes list" guidance it duplicated
already exists earlier in the prompt. Re-ran the Step 1 diagnostic against
the real Act PDF with the fix applied: **no change** — same shape as before
(one empty `content_block_delta`, then immediate `stop_reason: max_tokens`
with the full 4096-token budget consumed, `input_tokens` only slightly lower
at 30,072 vs 30,190, confirming the shorter prompt was actually used). This
rules out the system-prompt candidate. Root cause of the empty-output
failure is still unknown. Per instruction, stopped there — no pipeline run,
no regression check, no commit. The prompt edit itself is still live in
`classify_change.py` (harmless/arguably-correct cleanup, just not a fix).

## 2026-09-23 — Act table corrections applied (one-time data-quality fix, not a detected regulatory change)

Applied the 7 corrections identified in `docs/act_table_audit_2026-09-23.md`
to `db/dpdpa.db` via `scripts/apply_act_corrections_2026-09-23.py`. This is
**not** an automated pipeline change and not a new regulatory change — it
corrects DB text that diverged from the enacted Act at original seeding
time, per the audit above.

**Source verification:** the official Act PDF
(`https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf`)
was downloaded twice independently and confirmed byte-identical (SHA-256
`4deb2398...a7d15`), saved to
`docs/full_text/DPDP_Act_2023_official_2026-09-23.pdf`. Before applying the
corrections, this session independently re-extracted text from that
hash-verified copy and grep-checked every corrected passage's distinctive
wording against it directly (not just against the earlier same-session
extraction) — all 7 corrections' substantive text matches the primary
source verbatim (modulo PDF line-wraps).

**What changed:** `provisions.full_text` for `DPDPA-S7`, `DPDPA-S26`,
`DPDPA-S17`, `DPDPA-S28`, `DPDPA-S42`, `DPDPA-S44.1_3`, `DPDPA-S44.2` (7
rows); `provisions.current_summary` also updated for `DPDPA-S26`,
`DPDPA-S17`, `DPDPA-S44.1_3`, `DPDPA-S44.2` (4 of those 7). Each row's
`notes` field got an appended correction note, and `last_updated_date` was
set to today. Seven new `change_log` rows (`CHG-0033`–`CHG-0039`,
`change_type='Correction'`) record the before/after text for auditability.
`provisions.latest_change_id` was deliberately **not** repointed at these
new rows — `export_word.py`'s amendment-highlighting convention (yellow
highlight + strikethrough) means "the government just changed this," which
is not true here; verified post-run that all 7 rows still point at their
original `latest_change_id`. Provision count unchanged (79 before and
after) — confirmed by direct query.

**Review status:** every new `change_log` row is deliberately left
`review_status = 'Pending Review'` — no human has read the corrected text
line-by-line yet. This correction should be treated as a strong, verified
draft, not a closed item.

**Exports regenerated:** `docs/DPDP_Act_2023.docx` and
`data/DPDP_Rules_Tracker.xlsx` were regenerated from the corrected DB (new
modification timestamps confirmed). `docs/DPDP_Rules_2025.docx` was also
regenerated as a side effect of `export_word.py` running both exports in
one pass, but — since no Rules provisions were touched — it was left
uncommitted, matching the requested commit scope.

### Cost

$0 (mechanical script + local exports; no API calls this entry).

## 2026-09-23 — Full audit (Cowork), report only — NO code/DB/doc changes

Independent audit of the whole tracker; full report and all drafts in
`docs/audit_2026-09-23/` (start with `DPDP_Tracker_Full_Audit_2026-09-23.md`).
Nothing in `src/`, `db/`, `docs/*.docx` or `data/` was modified. Headlines:

- `docs/DPDP_Act_2023.docx` (committed in `fd476a7`) renders all 7 corrected
  Act rows with the amendment highlight + struck-through "Previous text
  (superseded)" — `export_word.py` never reads `latest_change_id`. Fix drafted
  and tested (`draft_code_fixes.patch`), not applied.
- Scheduled runs execute `main`, which has none of `fbd1c4e`/`fd476a7`;
  production had a silent source failure on 7 of 8 days (15–22 Sep).
- Corrigendum G.S.R. 892(E) (10 Dec 2025) confirmed from the MeitY-hosted
  Gazette PDF (SHA-256 8f8d9526…32f994); it fixes Rule 1(3)/(4), 13(5), 23(1)
  and Schedule typos. DB still holds the uncorrected text (draft script ready).
- Commencement dates verified against the primary G.S.R. 843(E) PDF — all
  correct; 13 Nov is the Gazette's face date (14 Nov = e-Gazette ID/digital
  signature only).
- Rules table (never checked before): all 23 Rules verbatim; Schedule
  Notes/illustration omitted; Third Schedule paraphrased.
- Act table: 12 further rows contain statements not in the Act (e.g. S8(4)
  invented condition, S22(3) invented proviso, S29(9) "section 18B", S37
  IT Act s.69A reference, S40 wrong rule-making list).
- Act PDF max_tokens: new theory — API buffers the single `changes` tool
  parameter, so the earlier "empty output" diagnostic could not distinguish
  "wrote nothing" from "wrote a huge list". Eager-streaming diagnostic drafted
  (not run). Warning: a "successful" call would auto-apply dozens of
  paraphrase "Corrections" via apply_change.py.
- Cost: $0 API.

## 2026-09-23 — Word export highlighting fix applied (Cowork, approved by Gautam) — uncommitted

- `src/export_word.py`: amendment highlighting now keys on
  `provisions.latest_change_id` instead of "newest non-'New Provision' change_log
  row". In plain words: our own data corrections (CHG-0033–CHG-0039) no longer
  show up in the Word document as if the government had amended the Act.
- `docs/DPDP_Act_2023.docx` regenerated from the unchanged `db/dpdpa.db`:
  verified 0 highlights, 0 strikethroughs, no "Previous text (superseded)"
  labels; corrected wording present. A simulated real amendment still
  highlights. Rules docx not regenerated.
- Gautam's decisions recorded for the follow-up Claude Code run
  (`docs/audit_2026-09-23/CLAUDE_CODE_PROMPT_apply_audit_fixes.md`): highlight
  only real regulatory changes and only the changed words (docx, Excel, email);
  G.S.R. 892(E) corrigendum treated as a regulatory change; rebuild all 48 Act
  rows verbatim from the official PDF; merge to `main` after all tests pass.

## 2026-09-23 — Applied all 9 phases of the audit fixes

This is the big one: every fix from the 23 Sep audit report, applied,
tested, and (once the remaining GitHub-side steps below are done)
released to production. In plain words, the two client-facing documents
and the daily automated check are now materially more trustworthy than
they were this morning — the Act text is verbatim instead of paraphrased,
a real government change is now told apart from us fixing our own
mistakes, and the pipeline can no longer lose a change silently.

### What changed, and why

- **Word/Excel/email now distinguish "the government changed the law"
  from "we fixed our own data".** A new `change_log.change_origin` column
  (`regulatory` / `data_correction` / `baseline`) drives this. Only a
  `regulatory` change is ever highlighted, and only the specific words
  that changed — not the whole clause — with a caption naming the source
  and date. This is what stopped the Word document from showing 7
  sections as "amended by the government" when we'd actually just
  corrected our own typos.
- **All 48 Act rows rebuilt word-for-word from the official PDF.** 46 of
  48 changed. The database held paraphrases before — some seriously
  wrong (a made-up "Companies Act" reference in s.22, a wrong TRAI Act
  citation in s.29, a fabricated IT-Act cross-reference in s.37, 24
  missing rule-making items in s.40). Every word now comes from the PDF
  through a script — never typed by hand — and passed six separate
  mechanical checks before being written. Full row-by-row detail:
  `docs/act_verbatim_rebuild_2026-09-23.md`.
- **The G.S.R. 892(E) corrigendum applied.** The government's own 10 Dec
  2025 correction notice — Rule 1(3)/(4)'s "of this Gazette" is now "in
  the Official Gazette", Rule 13(5)'s "Department" is now "Departments",
  Rule 23(1)'s cut-off sentence now correctly ends "...given in such
  order." This is a real regulatory change (the government issued it), so
  it's highlighted — the only 3 rows that are, right now.
- **Missing Rules Schedule text restored.** The First Schedule's
  consent-routing illustration and closing definitions, the Fourth
  Schedule's definitions note (relettered to match the corrigendum's
  fix for a printing defect in the original Gazette), the Third
  Schedule's two paraphrased rows replaced with the government's actual
  wording, and one dropped phrase in the Fifth Schedule. None of this is
  the government changing anything — it's us finishing work that was
  left incomplete at seeding — so it's recorded as a data correction,
  never highlighted.
- **3 of 5 pre-approved summary fixes applied** (commencement timing on
  two Act provisions, Rule 12's scope). The other 2 had already been
  rewritten differently since the audit was written — the script
  correctly refused to guess and left them alone; see "Open questions"
  below.
- **The pipeline can no longer lose a change silently.** A download
  failure now keeps the last good fingerprint instead of blanking it, and
  is reported instead of swallowed. A classification failure now rolls
  the fingerprint back so tomorrow's run retries instead of giving up
  forever. `pypdf` (which extracts text slightly differently between
  versions, enough to change a fingerprint) is now pinned to a tested
  version instead of auto-upgrading.
- **Classification redesigned to compare text first.** This is what was
  actually breaking the Act PDF check every single day: the AI was being
  shown the entire document on every run, which was both too large (it
  was hitting its reply-length limit before finishing) and stale (a
  60,000-character cutoff meant Sections 43, 44, and the Schedule were
  never even sent, and the Rules document's cutoff meant the AI saw
  almost nothing but Hindi). Now the pipeline compares the new fetch
  against what it saw last time, in plain Python, and only sends the AI
  the parts that actually changed. First-ever check of a source now
  correctly reports "baseline captured" and makes no AI call at all,
  rather than trying to classify the whole document as if it were new.
- **PIB source switched to its official RSS feed**, explicitly requesting
  English — the previous page could silently serve Hindi depending on the
  requesting server's apparent location, with no way to check from
  outside what GitHub's server would actually see.
- **A permanent automated test suite** (64 tests) now guards against all
  of the above regressing — including two tests that literally re-run
  the verbatim-text checks against the official PDFs on every test-suite
  run, so paraphrase can't quietly creep back in.
- **Documentation brought up to date**: `README.md` no longer describes
  OpenRouter (production has used Claude Haiku 4.5 since Sept 22); the
  daily check's schedule moved off the busy top-of-hour mark, where
  GitHub's own queue tends to delay it by hours; stale duplicate copies
  of the Act text that predated this fix were deleted so nothing
  still points at the old, wrong wording.

### Test results

- **64 automated tests, all passing** (`pytest tests/`): pipeline-failure
  handling, the diff-first classification design, highlighting
  correctness (including the exact G.S.R. 892(E) wording), and — the two
  permanent guards — every Act and Rules row checked verbatim against the
  official PDFs, and seeding a fresh database reproducing the committed
  text exactly.
- **A real, live run of the pipeline, twice**: real network fetches, real
  database writes, two real emails sent. First run correctly reported
  "baseline captured" for 3 sources with no AI calls; second run
  correctly reported no changes, also no AI calls. **Please confirm both
  emails arrived.**
- Documents regenerated and inspected by script: the Act Word document
  shows 0 highlights; the Rules Word document highlights exactly the 4
  corrigendum words and nothing else; the Excel Change_Log sheet has
  exactly 3 yellow rows.

### API cost

**Roughly $0.03 of the $1.50 budget spent, all Anthropic (Claude Haiku
4.5 / Sonnet 5) API calls:**

- ~$0.03: one diagnostic call re-running the exact production Act-PDF
  prompt with eager streaming, to settle the "was the model writing a lot
  or writing nothing" question from the earlier CHANGELOG entries.
  Result: the model completed normally this time (`stop_reason:
  tool_use`, 33 output tokens, empty change list) rather than hitting
  `max_tokens` — a different outcome from the earlier failures, most
  likely because the diff-first redesign means this failure mode can no
  longer occur in production regardless. Doesn't change anything that
  needs doing; recorded for the historical record.
- $0: both real end-to-end pipeline runs — the diff-first design means a
  source with no prior snapshot needs no AI call at all ("baseline
  captured"), and neither run found anything to actually classify.
- $0: everything else — all extraction, rebuilding, and verification work
  (Phases 3, 4a, 4b, 4c, and the whole test suite) is plain Python
  against PDF files, no LLM involved, per the ground rule that legal text
  only ever comes from a PDF through code, never from a model.

### Rows left at "Pending Review"

56 new rows this session (plus 7 pre-existing ones from before this
session, `CHG-0033`–`CHG-0039`, untouched): 46 from the Act rebuild, 4
from the Rules Schedule restoration, 3 from the G.S.R. 892(E) corrigendum,
3 from the summary fixes. `review_status = 'Pending Review'` on all of
them is intentional — per the project's no-human-review-gate design, this
doesn't block anything from being live and correct, but no human has yet
read the corrected text line-by-line. Recommended reading, in order of
how much changed: `docs/act_verbatim_rebuild_2026-09-23.md` (word-level
diffs for the biggest changes among the 46 Act rows), then the 7 rows
below.

### Open questions for EY legal (nobody has fixed or guessed at these — flagging only)

- **Rule 13(5)** names the "Ministry of Electronics and **Technology**"
  — missing "Information". Printed that way in the official Gazette and
  not touched by the corrigendum; kept verbatim.
- **Rule 14(3)** reads "...shall prominently publish...within a
  reasonable period...under its grievance redressal system..." with no
  stated object — publish *what*? Also printed that way in the official
  Gazette; kept verbatim.
- **13 vs 14 November 2026/2027** for the one-year/eighteen-month
  commencement dates: both source Gazette issues are dated "13th
  November" on their face, but the e-Gazette upload ID and digital
  signature timestamp say the 14th. The audit recommends treating 13 Nov
  as authoritative (the Act's own citation convention, 11 Aug 2023,
  follows the same face-date-vs-signature pattern) — this is a
  day-counting legal question, not a data error, and needs your read.
- **`DPDPA-S27.1d`** keeps the Act's own "; and" sentence ending verbatim
  rather than dropping it, per instruction pending your call:
  `"...impose penalty as provided in this Act; and"`.
- **Two small, newly-found transcription gaps**, both confirmed against
  the official PDF with two independent extraction tools (not extraction
  ambiguity, genuinely different from the database): `DPDPR-R10`(2)(c)
  ends with a period in the database where the Gazette has a semicolon;
  `DPDPR-SCH1` Part B item 4's lead-in is missing a colon ("The Consent
  Manager —" vs. the Gazette's "The Consent Manager: —"). Both are minor
  and outside every phase's stated scope this session, so left alone
  rather than fixed without the same verification rigor as everything
  else — your call whether they're worth a follow-up.
- **3 C2 cross-check exceptions** in the Act rebuild (`DPDPA-S8`,
  `DPDPA-S11`, `DPDPA-S33`) — sentences that only matched the second PDF
  tool's text after removing a known page-header/margin-note string.
  Expected and benign (pypdf mixes those into its text stream), listed in
  `docs/act_verbatim_rebuild_2026-09-23.md` for transparency.

### The MeitY timeline-compression proposal

Checked again today: MeitY held stakeholder consultations on 23 Jan 2026
proposing to cut the 18-month compliance timeline to 12 months for
Significant Data Fiduciaries (last date for compliance moving from 13 May
2027 to 13 Nov 2026), with industry feedback sought by 4 Feb 2026. As of
today, no formally notified amendment to the Rules has been found — this
remains a proposal under discussion, not a notified change. Worth
watching, and Phase 7's source-monitoring gap (no reachable feed for new
MeitY notifications) means this pipeline would not automatically catch it
if and when it is notified — see `fetch_sources.py`'s header comment for
what was tried.

### Not done — needs you or GitHub CLI access

This machine has no `gh` CLI installed and no GitHub token available, so
Phase 9's remaining steps — checking repo secrets, opening the PR,
triggering a workflow run, merging, tagging — could not be completed in
this session. See the final report for exactly what's left and the two
ways to unblock it.

## 2026-09-25 — eGazette fetch timeout raised (30s → 60s), uncommitted

Real production error from the Sep 24 06:17 IST daily run:

```
fetch failed for eGazette (https://egazette.gov.in/):
HTTPSConnectionPool(host='egazette.gov.in', port=443): Read timed out. (read timeout=30)
```

In plain words: the pipeline tried to download the eGazette homepage and
gave up after 30 seconds because the site hadn't answered yet. Gautam
manually opened the same page in a browser and confirmed it's genuinely
working, just slow — not down, not blocking automated requests, not
serving something unexpected. Since this looks like a real, working page
being cut off too early rather than a broken source, the fix is to give
it more time, not to investigate further right now.

**What changed:** `src/fetch_sources.py`'s `TIMEOUT` constant raised from
30 to 60 seconds. This is a single constant shared by every source's
fetch call (PIB, both MeitY PDFs, and eGazette), not a per-source
setting, so all four sources now get the longer allowance — harmless for
the fast sources, and gives the slow one twice the room it had.

**Why not something more elaborate:** the 23 Sep fixes already made this
failure mode safe even without a longer timeout — a fetch failure keeps
the last-known-good fingerprint and is reported by email, never
swallowed, so a slow eGazette day was never silently losing data or
going unnoticed. Doubling the timeout is the smallest change that
matches what was actually observed (a slow site, not a dead one). If
read timeouts keep happening even at 60 seconds, the next step would be
a short retry-with-backoff specifically for eGazette's fetch, not a
further blind increase in the wait time.

**Status: edited, not yet committed or pushed.** The file was changed
directly on Gautam's machine via the Filesystem device bridge. It still
needs `git add src/fetch_sources.py`, a commit, and a push to `main`
before it takes effect on the real GitHub Actions daily run — until that
happens, production is still running the old 30-second timeout, and
tomorrow's scheduled run could still time out the same way.

### Cost

$0 — a plain code edit, no API calls involved.
