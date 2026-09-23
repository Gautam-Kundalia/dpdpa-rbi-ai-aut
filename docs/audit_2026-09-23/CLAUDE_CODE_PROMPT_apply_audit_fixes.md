# Prompt for Claude Code: apply the 23 Sep 2026 audit fixes, test, then merge to `main`

Copy everything below the line into Claude Code, opened in `C:\Users\ASUS\dpdpa-rbi-ai-aut`.

---

You are working on the DPDP Regulatory Change Tracker in this repo (`C:\Users\ASUS\dpdpa-rbi-ai-aut`, branch `regulatory-change-pipeline`). It tracks India's DPDP Act, 2023 and DPDP Rules, 2025. Gautam Kundalia (EY) presents this database and its Word and Excel exports to clients as the legal text. **Treat any error in legal text as more serious than a code bug.**

Your job: apply every fix from the 23 Sep 2026 audit, test everything again, then merge the branch into `main` so the daily GitHub run uses the fixed code.

## 0. Read these first, in full, before changing anything

1. `docs/audit_2026-09-23/DPDP_Tracker_Full_Audit_2026-09-23.md`. This is the audit. Every task below comes from it.
2. `CHANGELOG.md`, the last four entries.
3. `docs/act_table_audit_2026-09-23.md`
4. `docs/audit_2026-09-23/draft_code_fixes.patch`, `DRAFT_apply_audit_fixes_2026-09-23.py` and `diagnose_act_pdf_eager_stream.py`. These are drafts. Use them as starting points, but re-check them, because some tasks below go further than they do.

**Working tree at the start.** Confirm this with `git status` before doing anything:

- `src/export_word.py`: **already fixed by the audit** (highlighting now keys on `provisions.latest_change_id`). Uncommitted.
- `docs/DPDP_Act_2023.docx`: regenerated with that fix (0 highlights). Uncommitted.
- `src/classify_change.py`: removes the old OpenRouter "Respond with ONLY a JSON object…" block from `SYSTEM_PROMPT`. Harmless cleanup. Uncommitted.
- `docs/DPDP_Rules_2025.docx`: only the file bytes changed; the text is identical to HEAD. Uncommitted.
- `pipeline-architecture-flow.html`: an uncommitted edit that wrongly says cron `30 0 * * *` means "04:30 UTC / 10:00 IST".
- `CHANGELOG.md`: a new audit entry at the end. Uncommitted.
- `docs/audit_2026-09-23/`: new, untracked.

If anything else differs, **stop and tell Gautam** before continuing.

## Decisions Gautam has made (follow these exactly)

- **D1. Highlighting rule.**
  - Only a **real regulatory change** is highlighted, meaning a change the government actually made to the law.
  - Only the **words that changed** get highlighted, not the whole provision. This applies everywhere a change is shown: the Word documents, the Excel tracker, and the notification email.
  - Changes *we* make to fix our own data (typos, wrong transcription, restoring omitted text, verbatim rebuilds, summary fixes) are **never** highlighted or reported as regulatory changes. They stay in `change_log` only as an audit trail.
- **D2. The G.S.R. 892(E) corrigendum (10 Dec 2025) counts as a regulatory change**, because the government issued it. So its specific corrected words are highlighted under D1.
  - Example: in Rule 23(1) only the word "order" is highlighted. In Rule 1(3)/(4) only "in the Official Gazette" is highlighted, with "of this Gazette" struck through.
  - If Gautam later says otherwise, flipping this must take a one-line change.
- **D3. Rebuild all 48 Act rows word for word from the official PDF** (option (a)). Keep `current_summary` as the plain-language field.
  - **Note:** the 22–23 Sep sessions did **not** do this. They corrected only 7 of 48 rows, and the other 41 still contain paraphrases and errors (audit §2).
- **D4. Merge to `main`** only after every fix is in and every test passes.
- **D5. Keep auto-apply with no human review gate.** This is an existing project decision; don't change it. But every document must describe it truthfully.

## Ground rules: these stop yesterday's mistakes happening again

1. **You write code; you never write legal text.** Every word of Act or Rules text that goes into the database must come out of the official PDF through a script: extracted, sliced and checked by code.
   - Never type, "fix", tidy, remember or reconstruct legal text yourself, even when you are sure what it says.
   - If the PDF has a quirk (for example, s.6(6) cross-refers to "sub-section (5)"), keep it exactly as printed.
2. **Only primary sources count.**
   - The Act: `docs/full_text/DPDP_Act_2023_official_2026-09-23.pdf`. SHA-256 must be `4deb23981d3010c8225a2ff6149e7243dc2268455b299e283afebdd7b72a7d15`.
   - The Rules: `docs/audit_2026-09-23/DPDP_Rules_2025_official_2026-09-23.pdf`, SHA-256 `eabc7d05e013144615d78ddc0e8b9c9aac1920e814f4fad38ce6560951f5aa08`.
   - The corrigendum: `docs/audit_2026-09-23/GSR892E_Rules_corrigendum_official.pdf`, SHA-256 `8f8d9526b511801889f8ae022b6d7c5db449283e90fe32792e5896314b32f994`.
   - The commencement notification: `docs/audit_2026-09-23/GSR843E_commencement_official.pdf`, SHA-256 `6df25cd8c76ac8eb18cae81835d51d51128ffbf2ed13262843395efddf0998e5`.
   - Verify every hash before use. If one doesn't match, stop.
   - **Never** use `docs/DPDP_Act_2023.docx`, `docs/full_text/*.md`, `graphify-out/` or the seed scripts as a source. They are all made from this same database, so using them would just copy the database back into itself.
3. **Every legal-text write is checked by code before it's committed** (see Phase 3's checks). A claim of "verbatim" without a passing mechanical check doesn't count.
4. **Don't rewrite summaries freely.** The 22–23 Sep summary rewrite *introduced* a new error: `DPDPA-S44.2` calls IT Act s.87(2)(ob) an "RTI-exemption clause", which it isn't.
   - Apply only the 5 pre-approved summary fixes in the draft script.
   - For any other summary that looks wrong, **list it for Gautam; don't change it.**
5. **Never touch** `effective_date` or `status` on existing rows. The audit verified all of them against G.S.R. 843(E).
6. **API budget: US$1.50 total for this task.** Log the cost of every Anthropic call (use the `usage` in each response and Haiku 4.5 pricing) in your final report. If you would go over, stop and ask.
7. **Git:**
   - First, tag the starting point: `git tag pre-audit-fixes-2026-09-23`, and back up the database to `db/backup/dpdpa_pre_audit_fixes_2026-09-23.db` (add that folder to `.gitignore`).
   - Make one commit per phase, with clear messages.
   - No force-pushes, no history rewriting, no `git add -A` that pulls in unrelated files.
8. **Stop and ask Gautam instead of guessing** if:
   - any check in Phase 3 or 4 fails and the reason isn't a documented extraction quirk; or
   - the Act or Rules PDF on MeitY's site no longer matches the stored hash; or
   - `ANTHROPIC_API_KEY` is missing from the GitHub secrets (Phase 9); or
   - a merge conflict isn't one of those listed in Phase 9; or
   - any test fails and you can't fix it without weakening the test.
9. **Explain in plain words.** Gautam isn't a software engineer. In the CHANGELOG and your final report, explain every change in simple language, and explain any technical term the first time you use it.

## Phase 1: Tidy up the working tree (one commit per item)

- Commit `src/export_word.py` and `docs/DPDP_Act_2023.docx`: "Stop rendering internal data corrections as regulatory amendments (export_word keys on latest_change_id)".
- Commit the `src/classify_change.py` SYSTEM_PROMPT cleanup.
- Revert `docs/DPDP_Rules_2025.docx` (`git checkout -- docs/DPDP_Rules_2025.docx`). Its text is identical to HEAD.
- Revert `pipeline-architecture-flow.html`, then change the schedule wording to: "scheduled 06:00 IST (00:30 UTC); in practice GitHub usually starts it ~4–5 hours later". Use the new time instead if Phase 9 changes the cron.
- Commit `docs/audit_2026-09-23/` and the CHANGELOG audit entry.

## Phase 2: Record where each change came from, and highlight only the changed words (D1, D2)

**Where each change came from.**

- Add a column `change_origin` to `change_log`, with the constraint `CHECK (change_origin IN ('baseline','regulatory','data_correction'))`.
- Update `db/schema.sql` for new databases, and add an idempotent migration in `db.py`'s `init_schema`. (Idempotent means safe to run twice: SQLite has no `ADD COLUMN IF NOT EXISTS`, so check `PRAGMA table_info` first.)
- Backfill existing rows:
  - `change_type='New Provision'` seed rows become `baseline`;
  - `CHG-0033`–`CHG-0039` become `data_correction`;
  - anything whose `detected_by` starts with `agent:` becomes `regulatory`.

**Word export (`export_word.py`).**

- A provision shows as amended only if it has an applied `change_log` row with `change_origin='regulatory'` and `change_type != 'New Provision'`.
- Render the provision's current `full_text` and highlight **only** the changed words. Compare that regulatory change's `old_full_text` and `new_full_text` word by word:
  - inserted or replaced words: yellow highlight;
  - removed words: grey strikethrough, shown inline just before the text that replaced them.
- Add a small grey caption: "Amended by <source_document> (<change_id>, <date>)".
- Remove the old whole-provision highlight and the separate "Previous text (superseded)" block.
- If the current `full_text` no longer contains that change's `new_full_text` (for example, a later data correction changed it), render it plainly with the caption, and log a warning.
- `data_correction` rows must never affect how anything is rendered.

**Excel export (`export_excel.py`).**

- Add `Change_Origin` to the Change_Log sheet.
- Fill **only** `regulatory` rows (excluding `New Provision`) in light yellow.
- On Master_Provisions, add a computed column `Last_Regulatory_Change` (a date and change_id, blank if none). Highlight that cell only, never the whole row.
- Rewrite the **README sheet** so it's true:
  - changes are applied automatically with no human review step;
  - `full_text` is verbatim from the official PDFs (true once Phases 3–4 pass);
  - Source_Log holds one row per source address, overwritten every run (no history);
  - highlighting means a government change only, and only the changed words.

**Email (`notify.py`).**

- The subject and body count only `regulatory` changes as "changes". For each one, show a short before/after snippet of just the changed words, for example: `Rule 23(1): "…given in such." → "…given in such order."`
- On days with errors, the first line must not say "No changes were detected". Say how many sources were actually checked successfully.
- Attach the documents only when a regulatory change was applied.

**`apply_change.py`.** Set `change_origin='regulatory'` on everything the pipeline applies.

## Phase 3: Rebuild all 48 Act rows word for word (D3), the careful part

**Starting point.** `docs/audit_2026-09-23/act_verbatim_draft.json` is a mechanical draft. **Don't trust it:** regenerate it with your own script and use it only to cross-check.

Write `scripts/rebuild_act_verbatim_2026-09-23.py` with `--dry-run` (the default) and `--apply` modes.

**Extraction**

- Check the Act PDF's SHA-256. If the network allows, download it again from `https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf` and confirm it's byte-identical. If the download is blocked, note that and carry on with the stored copy.
- Primary extractor: PyMuPDF text blocks. Drop the page header (block `y0 < 85`) and the side-margin notes (block `x0 < 115` or `x0 >= 480`). Keep the side-margin notes separately: they give each section's heading (e.g. "Certain legitimate uses.").
- Split into sections with a strict counter that expects 1, 2, 3 … 44 in order. The audit found that splitting on "any line starting with a number" once merged s.36 and s.37.
- The Schedule starts at "THE  SCHEDULE" (note the double space) inside the section 44 text.
- Drop chapter headings ("CHAPTER VI / POWERS, FUNCTIONS …"), the masthead and the signature block from the section bodies.

**Formatting, keeping each row's existing style**

- First line: `**Section N — <side-margin heading from the PDF, trailing full stop removed>**`.
- Then the Act text, one paragraph per clause or sub-clause, with a blank line between paragraphs.
- Join lines the PDF wrapped. Do **not** change words, punctuation, quote marks, "––" dashes, or capitals, apart from turning runs of spaces into single spaces.
- Keep every **Illustration** and **Explanation**, and every "or the rules made thereunder".
- For the Schedule (`DPDPA-SCHED`), rebuild the 3-column table (Sl. No. / breach / penalty). pypdf extracts it one column at a time, so match cells by position. Every cell's text must match the PDF exactly, including "May extend to …".

**Split rows (G.S.R. 843(E) puts these on different commencement dates)**

- `DPDPA-S6.1_8_10`: s.6 without sub-section (9), keeping all illustrations.
- `DPDPA-S6.9`: s.6(9) only.
- `DPDPA-S27.1a_c_e_2_3`: s.27 without clause (1)(d), keeping the lead-in "(1) The Board shall exercise and perform the following powers and functions, namely:—".
- `DPDPA-S27.1d`: the same lead-in, then "(d) …". Remove the trailing "; and" only if Gautam approves. Default: keep the text exactly and list it.
- `DPDPA-S44.1_3`: s.44(1) and (3). `DPDPA-S44.2`: s.44(2).
- **`DPDPA-S2`:** the database deliberately held only a subset of definitions. Under D3, replace it with **all 28 definitions** (a) to (zb), and remove the sentence "this tracker reproduces the terms most used…".

**Required checks. All must pass before `--apply` writes anything; the script exits non-zero otherwise.**

- **C1 Exact.** For each row, the text without the bold heading line, after normalising (collapse whitespace; convert curly quotes and dashes to plain ones; drop markdown `**`), must be a **contiguous substring** of the normalised PyMuPDF text of its section.
- **C2 Second extractor.** Every sentence of each row must also be found in the normalised pypdf text (split sentences on `.`, `;` and `:—`). pypdf mixes the side-margin notes and page headers into the text. So a sentence that fails C2 is only allowed if removing a known side-margin heading or page-header string from the pypdf text makes it pass. Print every such case.
- **C3 Completeness.** Joining all 48 rows in order (with the split rows put back together) must cover **≥ 99.5 %** of the words in the Act body (s.1 to the end of the Schedule). Print every uncovered stretch. Only chapter headings, side-margin headings, masthead, page headers and signatures may be left uncovered.
- **C4 Nothing made up.** None of these strings may appear in any row: `Bench`, `Companies Act`, `18B`, `69A`, `make good the loss`, `clearly distinguishable`, `signature of the Chairperson`, `not less than the prescribed period`, `Evidence Act`. Each was a fabrication found in the audit, and none is in the Act.
- **C5 Spot facts.** Test for exact phrases:
  - s.42(1) contains "to more than twice of what was specified in it when this Act was originally enacted";
  - s.8(4) begins "(4) A Data Fiduciary shall implement";
  - s.19(3) contains "social or consumer protection";
  - s.40(2) has items (a) to (z) (26 items) and contains "(y) the procedure for dealing an appeal under sub-section (8) of section 29";
  - the Schedule's 7 penalty amounts are exactly 250 crore, 200 crore, 200 crore, 150 crore, 10,000 rupees, "Up to the extent applicable…", and 50 crore.
- **C6 Untouched fields.** For all 48 rows, `effective_date`, `status`, `latest_change_id` and `sort_order` are byte-identical before and after.

**What `--apply` does (in one database transaction)**

- Update `provisions.full_text` for each row whose text changes, and set `last_updated_date`.
- Add to `notes`: " Text rebuilt verbatim <date> from the official Act PDF (SHA-256 4deb2398…7d15) — see docs/act_verbatim_rebuild_2026-09-23.md."
- For each changed row, insert a `change_log` row:
  - `change_type='Correction'`, `change_origin='data_correction'`;
  - `detected_by='manual:verbatim-rebuild-2026-09-23 (code-extracted, no model-written text)'`;
  - the before and after text in full, `review_status='Pending Review'`, `applied_to_master='Y'`.
- **Never** move `latest_change_id`.
- The 7 rows corrected on 23 Sep also get rebuilt, so they gain their missing Explanations and Illustrations.

**Make it reproducible**

- Write the verified text to `data/act_verbatim_2026-09-23.json`, with the PDF hash, extractor versions and date.
- Change `src/seed_dpdp_act_full.py` so `full_text` is loaded from that JSON instead of the hand-typed strings. Keep the summaries, topics and effective dates.
- Remove the misleading claim that `docs/DPDP_Act_2023.docx` is the source, and fix the "(verbatim)" print so it's true.
- Test: seed into a fresh temporary database and confirm it gives the same `full_text` as the rebuilt one.

**Review file.** Write `docs/act_verbatim_rebuild_2026-09-23.md`. For each row, show:

- the old-vs-new similarity score;
- which checks passed;
- a short word-level diff for rows with big changes.

Give a separate list of anything that needs Gautam's eye: the C2 exceptions, the "; and" endings on split rows, and any summary that now clearly contradicts the verbatim text (list it; don't fix it).

**Order:** run `--dry-run` first, read its output, then `--apply`. Do not apply if any check fails.

## Phase 4: Rules table

**4a. The G.S.R. 892(E) corrigendum, which counts as a regulatory change under D2.**

- Adapt `DRAFT_apply_audit_fixes_2026-09-23.py`: set `HIGHLIGHT_CORRIGENDUM = True`, and set `change_origin='regulatory'` on these rows. Before writing, **extract the corrected phrases from the corrigendum PDF by code** and check each one.
- The corrigendum's items are:
  - (i)(a),(b): Rule 1(3),(4), "of this Gazette" becomes "in the Official Gazette";
  - (ii): Rule 13(5), "Department" becomes "Departments";
  - (iii): Rule 23(1), "given in such" becomes "given in such order";
  - (iv)(a) First Schedule "everybody" becomes "every body". The database already has "every body", so no change;
  - (iv)(b) "(18 or 2013)" becomes "(18 of 2013)";
  - (v) Fourth Schedule Note: "." becomes ";" and "(a) to (f)" becomes "(a) to (g)".
- Point `latest_change_id` at these rows so they highlight, word level only.
- Add a `source_log` row for the corrigendum:
  - source 'MeitY';
  - url `https://www.meity.gov.in/static/uploads/2025/12/3c7ebbae0e5456f493f486e6845df86b.pdf`;
  - published_date 2025-12-11;
  - the content hash;
  - processing_status 'Processed';
  - its change IDs linked.
- Change `SRC-0003` (the commencement notification) to use the official URL `https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf` instead of `user-upload:…`.

**4b. Restore text that was left out at seeding.** These are data corrections: not highlighted, `change_origin='data_correction'`, text extracted by code from pages 24–41 of the Rules PDF (the English half).

- First Schedule: the Part B **Illustration** (P, B1, B2, Case 1 and Case 2) and the **Note** (definitions of body corporate, company/control/director/KMP, net worth, promoter/senior management). Use the corrigendum-corrected "(18 of 2013)".
- Fourth Schedule: the **Note**, with the corrigendum's relettering (a) to (g) and ";" applied.
- Third Schedule: replace "Same exceptions as above" and "Same three-year rule as above" with the full verbatim text for rows 2 and 3, and put back "(i)/(ii)" in the "user" definition.
- Fifth and Sixth Schedules: put back the paragraph headings ("Salary.", "Provident Fund.", "Leave." and so on).
- **Checks:**
  - every Rules row passes C1 and C2 against the English Rules text (after applying the corrigendum);
  - completeness is ≥ 99.5 % for rules 1–23 and Schedules 1–7;
  - `effective_date` and `status` are unchanged.
- Don't "fix" the wording oddities the corrigendum left alone: Rule 13(5) "Ministry of Electronics and Technology", Rule 14(3)'s missing object, and the preamble's "of the of the". Keep them verbatim, and list them in the report as open questions for EY legal.

**4c. Summaries.** Apply only the 5 pre-approved summary fixes from the draft script (`DPDPA-S6.9`, `DPDPA-S27.1d`, `DPDPA-S44.2`, `DPDPA-S44.1_3`, `DPDPR-R12`) as `data_correction`. The script aborts if the current summary isn't exactly what it expects; that's intentional.

## Phase 5: Stop changes being lost silently in the pipeline

- Apply `draft_code_fixes.patch`'s changes to `fetch_sources.py` and `run_pipeline.py`:
  - download errors go into `errors` (so the run exits 1 and the email says so);
  - the last good hash is kept when a download fails;
  - the previous hash is restored when classification fails, so the next run retries.
- **Pin `pypdf==6.19.0`** in `requirements.txt`. First confirm that this version reproduces the stored hashes: Act `f15bda1ff806…`, Rules `76094c7228c8…`. The audit showed pypdf 3.17.4 gives a different hash for the same file.
- Pin the other requirements to the versions you test with.

## Phase 6: Redesign classification to compare text first

Only send the AI what actually changed. This fixes the Act-PDF `max_tokens` failure, the 60,000-character cut-off, and the Rules classifier seeing only Hindi.

- **Store what was seen.** Add a table `source_snapshot(document_id PRIMARY KEY, content_hash, content_text, fetched_date)`, holding the extracted text from the last *successfully classified* fetch.
- **First run after this is deployed:** if there's no snapshot, store one and report "baseline captured". That's not an error, and it makes no AI call.
- **When a hash changes:** compare the previous snapshot with the new text line by line in plain Python (`difflib.unified_diff` on normalised lines, ±3 lines of context). Send Claude **only the changed passages**, plus only the provisions they plausibly touch. Match on section and rule numbers found in the changed passages; if none, send the provision list without full texts. Cap the prompt at about 20,000 characters.
- **For bilingual PDFs, drop mostly-Hindi changed passages** (Devanagari characters above 30 %) before sending, and note that in the log. The English text is what's authoritative for this tracker.
- **PIB:** the changed passages are new release titles. Before calling the AI, keep only titles that match `data protection|DPDP|personal data|MeitY|Electronics and Information Technology|Data Protection Board`. If none match, it's "No Change Detected" with no AI call.
- **Prompt (`SYSTEM_PROMPT`):** tell Claude that it's seeing *changed passages of the official source* and should report only changes the government made. **Never** report differences between our stored text and the source (that isn't its job). `Correction` means only an official corrigendum.
- **Model call:** `max_tokens=8192`. If `stop_reason == 'max_tokens'`, raise `ClassificationFailed` with that exact reason.
- **`_validate` rejects any change where:**
  - (for Amendment, Repeal, Clarification or Correction) `old_full_text` is not a substring of that provision's current `full_text`, after normalising; or
  - `new_full_text` is not a substring of the fetched text, after normalising.
- **`apply_change.py`:**
  - Replace **only the `old_full_text` span** inside `full_text`. It must match exactly once; otherwise raise and apply nothing. Never overwrite the whole provision with a clause.
  - Don't overwrite `current_summary` with the "what changed" line; that belongs in `change_log` only, and the email says the summary may need a human update.
  - For new provisions: `review_status='Pending Review'` (not 'Confirmed'), `effective_date` NULL with the note "commencement to be confirmed from the notification", `reference` taken from the provision_id pattern (e.g. `DPDPR-R24` becomes "Rule 24"), and `instrument_type='Schedule'` for `-SCH` ids.
- **Diagnostic.** With the new design, run `docs/audit_2026-09-23/diagnose_act_pdf_eager_stream.py` **once** against the *old* code path (about $0.05) and record what the model was trying to write. This settles the audit's theory for the record. Skip it if the budget is tight.

## Phase 7: Better sources for new notifications (time-boxed to 45 minutes)

Amendments come out as **new** Gazette notices, which the current sources can't see (audit §1.4).

- Find the official MeitY page that lists DPDP documents. It must be on MeitY's own domain, and you must confirm it currently lists G.S.R. 846(E), 843(E) and 892(E).
- Add it as a source that watches **only the list of document links**, not the whole page. A new link means: fetch that PDF, record it in `source_log`, and send it through Phase 6 as a new document.
- Also check whether PIB has an official MeitY-only RSS feed, or an English listing reachable by a plain GET request. If it does, and you've confirmed it's official and working, use it instead of `allRel.aspx`. That page shows only the current day's releases at the moment it's fetched, and may serve Hindi.
- Keep the eGazette home page as a weak signal, and document that it's weak.
- If you can't find a stable official endpoint, **don't invent one.** Write down what you tried in the CHANGELOG and move on.

## Phase 8: Tests

Add `pytest` and a `tests/` folder. All of these must pass:

- `test_legal_text_verbatim.py`: C1 to C5 for all 48 Act rows and C1/C2 for all 31 Rules rows, run against the committed database and the stored PDFs (checking their hashes). This is a **permanent** guard against paraphrase creeping back in.
- `test_highlighting.py`:
  - a `data_correction` produces 0 highlighted runs in the docx and 0 yellow cells in Excel;
  - a synthetic regulatory change highlights only the changed words (count the highlighted runs and check their text);
  - the G.S.R. 892(E) rows highlight exactly "in the Official Gazette" (×2), "Departments" and "order";
  - the email lists regulatory changes only.
- `test_pipeline_failures.py`:
  - a download error ends up in `errors` and gives exit code 1;
  - a classification failure restores the previous hash, and the next run retries;
  - `max_tokens` raises;
  - `_validate` rejects invented text;
  - `apply_change` replaces only the matching span and refuses when there are 0 or 2+ matches.
- `test_diff_first.py`: baseline capture, changed-passage extraction, dropping mostly-Hindi passages, the PIB keyword filter.
- `test_seed_reproducible.py`: seeding a fresh database from the scripts reproduces the committed `full_text`.

Then:

- **End-to-end, real run:** `python src/run_pipeline.py`. This sends a real email and makes real API calls within budget. The first run should say "baseline captured"; run it a second time and expect "No change" everywhere with no AI calls.
- **Regenerate the documents** (`export_word.py`, `export_excel.py`) and inspect them by script:
  - the Act docx has 0 highlights;
  - the Rules docx has highlights only on the corrigendum words;
  - the Excel Change_Log has yellow only on the 3 corrigendum rows;
  - the Excel README sheet has the new, truthful text.

## Phase 9: Documentation, then merge to `main`

**Documentation.**

- `README.md`: Claude Haiku 4.5, not OpenRouter; the diff-first design; `change_origin` and the highlighting rule; the truthful monitoring limits; no human review gate.
- `docs/act_table_audit_2026-09-23.md`: add a closing update.
- Stale copies:
  - regenerate `docs/full_text/*.md` from the database, or delete them. They're 31 Aug paraphrases, and nothing reads them (check with grep first).
  - Rerun graphify if it's installed. Otherwise delete `graphify-out/converted/DPDP_Act_2023_*.md`, because it holds the old, wrong Act text.

**CHANGELOG.** Add one plain-language entry covering all phases:

- what changed and why;
- test results;
- API cost;
- the rows left at "Pending Review";
- the open questions for EY legal (Rule 13(5) ministry name, Rule 14(3), 13 vs 14 Nov day-counting);
- the MeitY timeline-compression proposal (Jan 2026; no notified amendment found as of the audit).

**Workflow (`.github/workflows/daily-check.yml`).**

- Keep `main`'s `actions/checkout@v5` and `actions/setup-python@v6`, together with the branch's `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` settings and `if: always()`.
- Move the cron off the busy start of the hour: `"47 0 * * *"` (06:17 IST). Update the comment to say GitHub may still start it hours late.
- Keep the `permissions` block and the commit step as they are.

**Secrets.**

- Run `gh secret list` and `gh variable list`. `ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` and `NOTIFY_EMAIL` must exist.
- If `ANTHROPIC_API_KEY` is missing, **stop here.** Tell Gautam in plain steps: GitHub repo → Settings → Secrets and variables → Actions → New repository secret → name `ANTHROPIC_API_KEY`. Wait for him to confirm.
- `OPENROUTER_API_KEY` can stay for now. Mention that it's unused.

**Merge.**

1. Push the branch.
2. `git fetch origin`, then `git merge origin/main` into the branch. Expected conflicts:
   - `db/dpdpa.db`: take **ours**, the branch copy (`git checkout --ours db/dpdpa.db`). `main`'s daily bot commits only changed `source_log` dates and hashes, and the next run will refresh them;
   - `docs/*.docx` and `data/*.xlsx`: take ours, then regenerate them;
   - `daily-check.yml`: resolve as above.
   - Any other conflict: stop and ask.
3. Re-run the full test suite after the merge.
4. Push, and open a PR from `regulatory-change-pipeline` into `main` with `gh pr create`. The description should give a plain-language summary and link the CHANGELOG entry.
5. Run the workflow once on the branch (`gh workflow run daily-check.yml --ref regulatory-change-pipeline`). Wait for it with `gh run watch`, and confirm:
   - it succeeds;
   - its log shows Claude being used and "baseline captured" or "no change";
   - the bot commit lands on the branch;
   - the email arrives (ask Gautam to confirm).
6. **Merge the PR as a merge commit** (`gh pr merge --merge`; not squash, so the history is kept).
7. Run the workflow once on `main` (`gh workflow run daily-check.yml --ref main`) and confirm it succeeds in the same way.
8. Tag the result: `git tag audit-fixes-merged-2026-09-23` and push the tags.

## Final report to Gautam (in plain language)

1. What changed, phase by phase. For each: done, skipped, or blocked, and why.
2. Test results, and the result of each `gh run`.
3. How many Act and Rules rows changed, with a link to `docs/act_verbatim_rebuild_2026-09-23.md` and a list of the rows he should personally read (the `Pending Review` ones).
4. API cost, itemised.
5. Anything you stopped on, and anything still open.
6. One paragraph he can paste into the claude.ai Project knowledge (`logs/`) so the Project stays in sync.
