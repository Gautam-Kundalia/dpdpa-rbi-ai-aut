# Act table audit — 2026-09-23

Scope: mechanical, provision-by-provision re-diff of all 48 `DPDPA-*` rows in
`db/dpdpa.db` against a freshly downloaded copy of the tracked government
source (`https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf`,
fetched 2026-09-23). No AI calls were used for this step — the comparison is
pure Python (`pypdf` extraction + `difflib`), run against real, live data.
**No writes were made to `db/dpdpa.db` in this session** — see "Why no
corrections were applied" below.

> **Update, later the same day:** the corrections below were subsequently
> applied to `db/dpdpa.db` in a follow-up session, after further source
> verification. See "Corrections applied" at the end of this document — the
> analysis, caveats, and severity judgments below remain the record of how
> the corrections were derived and are still worth reading in full.

## Why this audit happened

Tonight's session started from a working theory in `CHANGELOG.md`: the Act
PDF classifier has never succeeded, and the leading guess was that the model
was trying to report an unusually large number of real Act/DB mismatches in
one call and running out of output budget (`max_tokens`) before it could
finish. Step 1 (a live, streaming diagnostic against the real Anthropic API,
cross-checked at the raw SSE wire level to rule out an SDK artifact) found
the opposite: the model consumes its entire 4096-token output budget while
emitting **zero** visible tool-call JSON — one empty `input_json_delta`, then
immediate `stop_reason: max_tokens`. That refutes "the model is mid-writing
many legitimate diffs" as the mechanism. This Step 2 audit was run anyway
because it is free (no LLM cost) and independently tests part of the same
premise: *is the DB's Act text actually far off from the live PDF?*

**It is — more so, and in a more concerning way, than the "3 of 5
spot-checked sections had defects" finding this audit was meant to verify.**

## Method and its limits

- `_extract_text()` (the exact function `fetch_sources.py`/`classify_change.py`
  use in production) was reused to pull PDF text.
- The government PDF is a bilingual (Hindi/English) Gazette document with
  running page headers/footers, a one-time masthead block, and per-section
  marginal catchword annotations (e.g. "Short title and / commencement.")
  that `pypdf`'s linear text extraction interleaves into the section body
  text, since it has no concept of page columns. A best-effort noise filter
  strips the masthead, page headers/footers, and `Illustration(s).` markers.
  It does **not** reliably strip the per-section marginal catchwords (a
  denylist would require ~44 hand-curated entries and risks deleting
  genuine short clause fragments that have the same shape) — these still
  show up in the raw diffs as harmless noise and were discounted by eye
  during review, not automatically.
- Section boundaries were found via a strict monotonic state machine (expect
  1, then 2, then 3, ... 44 in order) rather than "any line starting with a
  number," after an earlier version of this script silently merged Sections
  36 and 37 because "37." happened to land mid-line in the extracted text
  rather than at a line start.
- A `similarity` ratio (`difflib.SequenceMatcher.ratio()`, on whitespace/
  quote/dash-normalized text) is reported per row as a **triage signal
  only** — not a certified diff. Low similarity often reflects heavy
  condensation (the DB drops illustrations, explanatory provisos, and
  cross-references that the Act includes) rather than wrong content. Every
  row below was read by hand; the verdicts below are the actual finding,
  not the raw score.
- Four rows (`DPDPA-S6.9`, `DPDPA-S27.1d`, `DPDPA-S44.1_3`, `DPDPA-S44.2`)
  score artificially low because the script compares split sub-clause rows
  against the *entire* parent section's PDF text (it doesn't know how to
  slice by sub-clause) — this is a tooling limitation, not a finding.
- `DPDPA-SCHED` initially scored 0.0 only because "Schedule (Act)" doesn't
  match the `Section N` regex used to locate its PDF counterpart, so no
  comparison ran at all. Manually re-pairing the Schedule's table cells
  (pypdf extracts the PDF's 3-column penalty table column-by-column, not
  row-by-row, so the "nature of breach" list, the serial-number list, and
  the penalty-amount list appear as three separate blocks) confirms all 7
  rows' penalty amounts match the live PDF exactly. **`DPDPA-SCHED` is
  correct** (wording is paraphrased, e.g. "give... notice" vs "notify," but
  the substance and all 7 monetary figures match).

## Headline finding

Two different things are true at once, and the report separates them:

1. **Nearly every one of the 44 sections is a condensed paraphrase of the
   Act, not a verbatim transcription** — illustrations, explanatory
   provisos, "Explanation.—" clauses, and cross-references are routinely
   dropped. `DPDPA-S2`'s own text says so explicitly ("this tracker
   reproduces the terms most used elsewhere in it; consult the Act's full
   text for the complete list of 28 defined terms"). This is *by design*,
   not a defect, and it is why the classifier's system prompt instruction
   to "quote VERBATIM clause text... from... the provided current
   provisions" is already somewhat at odds with the DB's own content for
   most rows — a separate, real issue from tonight's `max_tokens` failure,
   worth a follow-up.

2. **A meaningful number of sections don't just condense — they say
   something different from the enacted Act.** Six of these were confirmed
   by direct text comparison against the freshly fetched, live PDF (not
   inferred from the low similarity score alone):

### Confirmed substantive errors (verified against the live PDF text)

| Row | What the DB says | What the Act actually says | Why it matters |
|---|---|---|---|
| `DPDPA-S26` | Chairperson's powers structured as three numbered sub-sections (1)/(2)/(3), the third being authority to **"constitute Benches... comprising one or more Members"** | The Act structures this as three lettered clauses (a)/(b)/(c) — general superintendence, authorising an officer to scrutinise complaints, and authorising a Member/group of Members to conduct proceedings — with **no mention of "Benches" anywhere** (confirmed: zero matches on a full-text search of the fresh PDF extraction for "Bench"). | The word "Benches" and the DB's whole (1)/(2)/(3)-with-proviso structure is not Act language, regardless of what happened to the underlying power. Provenance of this specific wording is unknown — see below, the seed script's own listed source turned out not to be independent. |
| `DPDPA-S7` | Ground (b)(ii) for the State's processing: **"such processing is in accordance with any policy... or any standards prescribed for that purpose"** | Ground (b)(ii) is actually about personal data **already held in a government database/register** ("such personal data is available in digital form in, or... digitised subsequently from, any database, register, book or other document... maintained by the State... and is notified by the Central Government"). Different legal test entirely. | A consultant citing DB's (b)(ii) would describe the wrong condition for lawful State processing under this ground. |
| `DPDPA-S17` | (1) lists Chapter II/III as excluded, **omits "and section 16"** that the Act excludes too. (3)/(4)/(5) appear to conflate two different Act provisions (a start-up carve-out limited to specific sections, and a general 5-year sunset power) into one garbled sub-section, and (4) drops the exemption for personal-data-correction rights (section 12(2)) that the Act actually includes. | See live PDF sub-sections (1), (3), (4), (5) for the actual text. | Exemption scope is safety-critical for compliance advice; both the missing "section 16" exclusion and the conflated (3)–(5) understate/misstate which obligations a Data Fiduciary is actually exempt from. |
| `DPDPA-S28` | (5) introduces a **"notice... calling upon it to justify why an inquiry should not be initiated"** step, and (7)(c) cites **specific Indian Evidence Act, 1872 sections 123/124** | Neither the show-cause-notice step nor the Evidence Act citation appears anywhere in the Act's actual Section 28. The Act's (7)(b) is just "receiving evidence of affidavit requiring the discovery and production of documents," with no Evidence Act cross-reference. | Invents a procedural right/step for respondents and a statutory citation that isn't in the enacted law. |
| `DPDPA-S42` | (1): penalties under the Schedule are capped **"in aggregate... at two hundred and fifty crore rupees at any given time"** | (1): the actual restriction is that no amendment **"shall have the effect of increasing any penalty... to more than twice of what was specified in it when this Act was originally enacted"** — a per-penalty doubling cap, not a flat aggregate ceiling. | These are different rules with different legal effect. Confirmed by direct extraction (see PDF lines around "42. (1)"). This is the single clearest, most legally consequential mismatch found. |
| `DPDPA-S44.1_3` / `DPDPA-S44.2` | TRAI Act amendment: DB says a new sub-clause (iii) is **"inserted"** after existing (i)/(ii). IT Act amendment: DB says the Patents Act reference in s.81's proviso is **"substituted."** | Both are wrong in the same specific way the original spot-check already flagged: the Act's actual amendment machinery **substitutes** clauses (i) and (ii) of the TRAI Act wholesale with a new three-item list (referencing the IT Act 2000, the Airports Economic Regulatory Authority Act 2008, and the DPDP Act), and **inserts** (not substitutes) the DPDP Act reference into IT Act s.81's proviso. The DB has "inserted" and "substituted" backwards for these two respectively, and is missing the TRAI Act's Airports Economic Regulatory Authority Act reference entirely. | This is exactly the "'substituted' vs 'inserted'" defect flagged in `CHANGELOG.md`'s prior spot-check — now confirmed to recur, not a one-off. |

### Everything else (39 rows)

The remaining rows range from near-exact (`DPDPA-S38`, `DPDPA-S41`: wording
only, similarity > 0.9) to heavily condensed but not contradicted
(`DPDPA-S8`–`S25`, `S29`–`S36`, `S39`, `S40`, `S43`: DB keeps the operative
rule but drops illustrations, explanatory provisos, and some cross-
references). None of these were found to state something the Act doesn't —
but given how the six rows above were found (by reading, not by the
similarity score alone), the honest statement is: **the remaining rows were
reviewed at a normal level of care, not the same line-by-line scrutiny given
to the flagged six, and a further, dedicated human legal review of all 44
sections is warranted** before this table is treated as authoritative. The
full mechanical diff for every row (including the ones summarized here) is
preserved in the session scratchpad and can be regenerated cheaply (~$0, no
LLM calls) from the government PDF at any time.

## Provenance check: the seed script's own listed source is not independent

`src/seed_dpdp_act_full.py` sets `DOCX_PATH = "docs/DPDP_Act_2023.docx"` and
records it as each provision's `full_text_path` — implying it's the source
document the seed text was transcribed from. It is not: extracting
`docs/DPDP_Act_2023.docx` and checking it against the two clearest confirmed
errors above (Section 26's "Benches" clause, Section 42's aggregate-cap
wording) shows the DOCX matches the **DB's** wording verbatim — down to the
tracker's own "Status: Active | Effective: ..." and "Note: Currently in
force." annotations, which are this tracker's metadata, not anything a
government PDF would contain. In other words, `docs/DPDP_Act_2023.docx`
appears to be an export/mirror of this same database (most likely
`export_word.py`'s output), not an independent verbatim copy of the Act —
so it cannot corroborate or rule out any theory of where the divergent text
originated. **Provenance of the confirmed-wrong wording is unknown.** An
earlier-draft-Bill origin was our first guess while writing this report, but
it was never actually checked against a draft Bill text and has been
removed as unsupported — it should not be treated as an established fact by
anyone reading this document.

## Why no corrections were applied (Step 3 not attempted)

Per the task brief's own instruction — "if ANY section's correct reading is
ambiguous or you're not confident, do NOT guess": six confirmed errors,
unknown provenance, and no second independent human legal reviewer in this
session together mean that applying corrections from a single mechanical
diff pass risks introducing new errors under the guise of fixing old ones —
this is master legal text a real compliance consultant relies on. **Step 3
(writing corrections into `provisions.full_text`) was deliberately not
attempted tonight.**

## Bearing on the original `max_tokens` theory

This audit independently confirms real, substantive mismatches exist beyond
the 5 originally spot-checked sections — but it does not corroborate the
specific mechanism CHANGELOG.md guessed at (the model running out of budget
*while writing* many legitimate diffs). Step 1's raw-SSE-verified finding
was that the model writes essentially nothing before exhausting its budget.
Whether the sheer size/messiness of the "current provisions" context (48
rows × up to 2000 chars each, mixed with a 60k-char freshly fetched PDF
dump) is itself the trigger — as opposed to diff *volume* — is a separate,
still-open question for a future session.

One concrete, free-to-try candidate for that follow-up: `classify_change.py`'s
`SYSTEM_PROMPT` still ends with "Respond with ONLY a JSON object of the
exact shape... No prose, no markdown fences — just the JSON object" — an
instruction left over from the OpenRouter/loose-JSON era that now
contradicts `tool_choice` forcing the response into a tool call's `input`
(there is no place for "a JSON object" to appear outside the tool input
under forced tool use). It isn't sufficient on its own to explain the
failure (Rules/PIB/eGazette carry the same instruction and work), but it's
a real, no-cost-to-fix defect worth stripping before spending further API
budget chasing the `max_tokens` cause.

> **Update:** this candidate was tried in a follow-up session the same
> night. The instruction was removed from `SYSTEM_PROMPT` and the Step 1
> diagnostic was re-run against the real Act PDF — no change in behavior
> (still one empty delta, then immediate `stop_reason: max_tokens` with the
> full output budget consumed). The candidate is ruled out; root cause of
> the empty-output failure remains open. See `CHANGELOG.md`.

## Corrections applied — 2026-09-23 (follow-up session)

The 7 corrections identified above were applied to the real `db/dpdpa.db` in
a follow-up session the same night, via
`scripts/apply_act_corrections_2026-09-23.py`. Full detail is in
`CHANGELOG.md`; summarized here for anyone reading this audit document on
its own:

- **What was corrected:** `provisions.full_text` for all 7 flagged rows
  (`DPDPA-S7`, `DPDPA-S26`, `DPDPA-S17`, `DPDPA-S28`, `DPDPA-S42`,
  `DPDPA-S44.1_3`, `DPDPA-S44.2`); `provisions.current_summary` also
  updated for 4 of those 7 (`DPDPA-S26`, `DPDPA-S17`, `DPDPA-S44.1_3`,
  `DPDPA-S44.2`) where the old summary described the wrong content.
  `DPDPA-SCHED` was **not** touched — it was already verified correct above.
- **How it was verified before applying:** the tracked Act PDF was
  downloaded twice independently in a prior step and confirmed
  byte-identical (SHA-256 `4deb2398...a7d15`), saved to
  `docs/full_text/DPDP_Act_2023_official_2026-09-23.pdf`. Before running the
  correction script, this session independently re-extracted text from that
  specific hash-verified file (a second, independent extraction pass beyond
  the one used to originally build this audit) and directly grep-verified
  every corrected passage's distinctive wording against it — all 7
  corrections match the primary source verbatim, modulo PDF line-wrapping.
  This is in addition to whatever review passes produced the corrected text
  itself (the correction script's `detected_by` field and this repo's
  session history attribute that to a Sonnet+Opus-assisted review).
- **Auditability:** each correction is recorded as its own `change_log` row
  (`CHG-0033`–`CHG-0039`, `change_type = 'Correction'`) with the full
  before/after text, rather than being silently overwritten.
  `provisions.latest_change_id` was deliberately left pointing at each row's
  original change — these corrections are not "the government changed the
  law," and must not trigger `export_word.py`'s amendment-highlighting
  convention.
- **review_status is deliberately `'Pending Review'`** on all 7 new
  `change_log` rows. No human has yet read the corrected text line-by-line
  against the Act. Treat this as a strong, source-verified draft correction,
  not a closed item — the next step is that human read-through, not further
  automated changes.
