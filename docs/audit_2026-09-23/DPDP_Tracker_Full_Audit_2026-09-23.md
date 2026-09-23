# DPDP Regulatory Change Tracker: full audit, 23 Sep 2026

**Scope.** Branch `regulatory-change-pipeline` at `fd476a7`, your working copy at `C:\Users\ASUS\dpdpa-rbi-ai-aut`, and `main` on GitHub (the branch that actually runs every day).

**Method.** I read the code and database directly from your computer. The government PDFs were downloaded fresh from MeitY's own server through the in-app browser and hashed. (A "hash" is a digital fingerprint: if even one byte changes, the fingerprint changes.) I extracted the text myself with two different PDF tools and compared it against the database word by word.

**What I did not change.** I made **no changes to your database, code, or client documents**. Every fix below is a draft for you to approve.

**Cost.** $0 of API credit.

**Sources used (all primary, with their fingerprints):**

| Document | Where from | SHA-256 |
|---|---|---|
| DPDP Act, 2023 | meity.gov.in/…/2024/06/2bf1f0e9….pdf | `4deb2398…a7d15` (identical to tonight's copy) |
| DPDP Rules, 2025 (G.S.R. 846(E)) | meity.gov.in/…/2025/11/53450e6e….pdf | `eabc7d05…f5aa08` |
| Commencement notification G.S.R. 843(E) | meity.gov.in/…/2025/11/c56ceae6….pdf | `6df25cd8…0998e5` |
| **Rules corrigendum G.S.R. 892(E)** | meity.gov.in/…/2025/12/3c7ebbae….pdf | `8f8d9526…32f994` |

---

## 1. Read this before any client or senior meeting today

### 1.1 The Act Word document shows 7 sections as "amended by the government". They weren't.

`docs/DPDP_Act_2023.docx` (committed and pushed in `fd476a7`) shows Sections 7, 17, 26, 28, 42, 44(1),(3) and 44(2):

- in **yellow highlight**, and
- with the **old, wrong text** shown underneath, crossed out, under the label **"Previous text (superseded)"**.

So a reader sees the made-up "Benches" wording, the ₹250 crore overall penalty cap and the Evidence Act citations presented as law that the government replaced. I counted this directly in the file: 7 "superseded" labels, 48 highlighted text runs.

**Why it happened.** CHANGELOG says the corrections "must not trigger" highlighting because `latest_change_id` was deliberately left alone. But `export_word.py` never reads `latest_change_id`. It highlights the newest change-log row that isn't a "New Provision", and a "Correction" row qualifies.

**Draft fix (tested, not applied).** Make `export_word.py` decide highlighting from `provisions.latest_change_id`, which is what the CHANGELOG assumed it did.

- Tested on a copy of your database: the Act document then shows **0 highlights**, with the corrected text shown normally.
- Tested with a simulated real amendment: it still highlights correctly.
- The change is in `draft_code_fixes.patch`. After applying it, re-run `export_word.py` and commit the new Act document.

**Until then, don't show that file.**

### 1.2 The daily run is not running any of the fixes you've been told about

GitHub only runs *scheduled* workflows from the default branch, which is `main`. `main` is behind the branch by 13 files: none of `fbd1c4e` (the silent-failure fixes and the switch to Claude) or `fd476a7` (the Act corrections) is on it.

- Production still calls OpenRouter.
- It still has the silent-failure bugs.
- It still holds the uncorrected Act text.

Here is what production actually recorded (read from the database `main` commits every day):

| Day (UTC) | PIB | eGazette | GitHub showed |
|---|---|---|---|
| 15 Sep | Error (×2), then New | New | success |
| 16 Sep | **Error** | New | success |
| 17 Sep | **Error** | New | success |
| 18 Sep | New | **Error: could not download at all** | success |
| 19 Sep | New | **Error: could not download at all** | success |
| 20 Sep | New | New | success |
| 21 Sep | New | **Error** | success |
| 22 Sep | New | **Error** | success |

"New" here means the old "stuck on New" bug. The Rules and Act PDFs never changed, so they were never sent to the AI. **In 8 days, production applied 0 changes, and on 7 of those 8 days at least one source failed silently.**

**What you can honestly say today:** "the fixes are built and tested, and deploying them is pending."

### 1.3 The "possible corrigendum" is real, and the database never picked it up

A corrigendum is a formal government notice that corrects printing mistakes in an earlier notification. This one is **G.S.R. 892(E)**:

- dated 10 Dec 2025,
- published in Gazette Extraordinary No. 806 on 11 Dec 2025,
- e-Gazette ID `CG-DL-E-12122025-268455`,
- hosted on MeitY's own server.

It makes eight corrections to G.S.R. 846(E) (the DPDP Rules). Quoted directly from the PDF:

- "(i) in page 24,– (a) line 22, for 'of this Gazette', read 'in the Official Gazette'; (b) line 24, for 'of this Gazette', read 'in the Official Gazette'". These are Rule 1(3) and 1(4), so **the Rule 1(2) vs 1(3)/(4) inconsistency is resolved**.
- "(ii) in page 29, line 44, for 'Department', read 'Departments'". This is Rule 13(5), so **the singular/plural defect is resolved**.
- "(iii) in page 32, line 4, for 'given in such', read 'given in such order'". This is Rule 23(1), so **the cut-off sentence is resolved**.
- "(iv) in page 34, (a) … for 'everybody', read 'every body'; (b) … for '(18 or 2013)', read '(18 of 2013)'". These are in the First Schedule.
- "(v) in page 38, (a) … for '.', read ';' and (b) … for '(a) to (f)', read '(a) to (g)'". This is the Fourth Schedule Note, which printed two items both labelled "(a)".

What this means for the database:

- `DPDPR-R1`, `DPDPR-SDF-R13` and `DPDPR-R23` still hold the uncorrected text. There's a before/after draft in `DRAFT_apply_audit_fixes_2026-09-23.py`.
- The First and Fourth Schedule Notes aren't in the database at all (see §3).

**Decision for you:** a corrigendum *is* a government action. Should it get the yellow "amendment" highlight or not? The draft script won't run until you choose.

**The bigger lesson:** the corrigendum was published as a *separate* Gazette notification. The tracker only watches the original Rules PDF for changes, so it could never have caught this, and it won't catch a future amendment either (see 1.4).

### 1.4 What the tracker can and can't actually detect

"It automatically monitors DPDP changes" isn't a safe claim yet.

- **The MeitY PDFs.** The tracker only notices if someone edits *those two exact files*. Amendments and corrigenda are published as *new* notifications, so they never change those files.
- **The eGazette home page.** It lists only the **4 most recent** Extraordinary Gazettes, from every ministry, with subjects cut short. IDs went from 268455 in Dec 2025 to 276410 today, which is roughly 28 new Gazettes a day. A DPDP notice would be pushed off that list within hours, and a once-a-day snapshot will almost never catch it.
- **The PIB listing.** `allRel.aspx` shows **only today's releases, as of the moment it's fetched**. When I checked it at 07:51 IST today it said "0 releases" for 23 Sep. The run starts around 10:30 IST, so anything released later in the day is never seen. From an Indian browser the page also switched to Hindi (`lang=2`). I couldn't confirm what language GitHub's server receives.
- **The Rules PDF text the AI actually reads.** The extracted text is 120,816 characters, and the Hindi version comes first. The English starts at character 58,222. The classifier only receives the first 60,000 characters, so **it sees roughly 58,000 characters of garbled Hindi and about 1,800 characters of English** (the preamble, Rule 1 and the start of Rule 2). An amendment to Rules 2–23 or any Schedule would reach the AI as text it cannot compare. The Act is cut off partway into Section 42, so 43, 44 and the Schedule are never sent.

**Proof by example.** MeitY consulted on shortening the 18-month timeline to 13 Nov 2026 (Jan–Feb 2026; [Chambers / S.S. Rana](https://chambers.com/articles/meity-plans-to-cut-short-dpdp-compliance-timeline-and-notify-cross-border-restrictions-for-sdfs)). None of the tracker's sources would reliably catch that if it were notified.

- I found **no notified amending instrument**, and two trackers updated 21 Sep 2026 agree ([dpdprules.org](https://dpdprules.org/timeline), [ConsentOS](https://consentos.in/learn/dpdp-compliance-timeline/)).
- That is secondary evidence, not proof it doesn't exist. **Say the dates are "as notified", and mention that a compression proposal was floated.**

### 1.5 The client-facing Excel README describes things the code doesn't do

The README sheet in `DPDP_Rules_Tracker.xlsx` says:

- every provision is kept "in its current, correct form";
- full text is "Verbatim … never duplicated or paraphrased";
- step 3 of the workflow is a human "Review … until a consultant checks it".

The code auto-approves with no confidence threshold (`review_status='Approved', reviewed_by='auto'`). The Act text is mostly paraphrased, and the Rules miss the corrigendum. The walkthrough doc and the repo README correctly say "no human review gate". The Excel README is the one that's out of line. It also calls Source_Log "one row per source document". It's actually one row per web address, overwritten every day, so there's no history.

### 1.6 Commencement dates: verified correct against the primary notification

These are the dates when each part of the law switches on. From G.S.R. 843(E) (Gazette Extraordinary No. 757):

> "(a) the date of publication of this notification … sub-section (2) of section 1, section 2, sections 18 to 26 sections 35, 38, 39, 40, 41, 42, 43, and sub-sections (1) and (3) of section 44 …; (b) one year from the date of publication … sub-section (9) of section 6 and clause (d) of sub-section (1) of section 27 …; (c) eighteen months from the date of publication … sections 3 to 5, sub-sections (1) to (8) and (10) of section 6, sections 7 to 10, sections 11 to 17, section 27 except clause (d) of sub-section (1) …, sections 28 to 34, 36, 37 and sub-section (2) of section 44"

- **All 48 Act rows' effective dates match.** I checked this by script.
- All 31 Rules rows match Rule 1.
- One small nit: `DPDPA-SCHED`'s note says the Schedule is in "group (c)" of G.S.R. 843(E). The notification doesn't mention the Schedule at all. The Schedule works through s.33, which does start in group (c).

**13 or 14 November?** The evidence points to **13 Nov**. Here's what each document shows:

- Both Gazette issues (843(E) and 846(E)) are dated on their face "THURSDAY, NOVEMBER 13, 2025", and both notifications say "New Delhi, the 13th November, 2025".
- The "14" comes from two things:
  - the e-Gazette upload IDs (`CG-DL-E-14112025-…`);
  - the digital signatures ("Date: 2025.11.14 10:43:53 +05'30'" on the Rules; 10:37 IST on 843(E)).
- The Act itself follows the same pattern. Its face date is 11 Aug 2023, but its digital signature is dated 12 Aug 2023, 02:14 IST. Everyone cites the Act as 11 Aug 2023.

So I'd keep 13 Nov. Whether "one year from" 13 Nov 2025 lands on 13 or 14 Nov 2026 is a day-counting question for EY's legal team. It's not a data error.

### 1.7 Summary errors a client could read

| Row | What it says now | What's correct | Source |
|---|---|---|---|
| `DPDPA-S6.9` | "commences **a year after** the rest of Section 6" | It commences **6 months before** the rest (13 Nov 2026 vs 13 May 2027) | G.S.R. 843(E)(b) vs (c) |
| `DPDPA-S27.1d` | "Commences **a year after** the rest of Section 27" | Same problem: 6 months before | same |
| `DPDPA-S44.2` (rewritten tonight) | s.87(2)(ob) is "a now-redundant **RTI-exemption clause**" | IT Act s.87(2)(ob) is the rule-making power for "the reasonable security practices and procedures and sensitive personal data or information under section 43A" | [IT Act s.87(2)](https://indiankanoon.org/doc/1212882/) |
| `DPDPR-R12` | exempts only from the "prohibition on tracking…" | Exempts from **both** s.9(1) (verifiable parental consent) and s.9(3). Rule 12: "sub-sections (1) and (3) of section 9 … shall not be applicable" | Rules PDF |
| `DPDPA-S44.1_3` (rewritten tonight) | RTI change is to "add" an exemption | Both are **substitutions**: "for clause (j), the following clause shall be substituted" | Act s.44(3) |

Draft replacements for all five are in the draft script.

---

## 2. Act table: all 48 rows re-checked word for word

Each row was compared against the margin-free PyMuPDF extraction. Every flagged phrase was then re-confirmed with pypdf, a second PDF tool. Both tools agree on every item below. Full side-by-side comparison: `act_db_vs_pdf_side_by_side.txt`.

**The 7 rows corrected tonight** (S7, S17, S26, S28, S42, S44 ×2) now match the PDF. S26, S28, S42 and S44 are exact. In S7, s.7(e) says "any law in force outside India" where the Act says "any law for the time being in force outside India", and the "disaster" Explanation is dropped. That's minor.

**Close enough or exact (no substantive issue):** S1, S2 (a declared subset of the definitions), S4, S6.9, S10, S13, S14, S15, S24, S25, S27(1)(d), S30, S31, S33, S34, S35, S36, S38, S41, and the Schedule (all 7 amounts correct).

**Rows that say something the Act does not say.** These are new findings beyond tonight's audit. All quotes are from the PDF.

| Row | What the database says | What the Act says | Risk |
|---|---|---|---|
| S8(4) | "**Where** personal data … is likely to be processed for any purpose not related to sub-section (3), the Data Fiduciary shall implement…" | "(4) A Data Fiduciary shall implement appropriate technical and organisational measures…" There's **no condition**: the duty always applies. | **High** |
| S6(3) | consent request must be "**clearly distinguishable**" | Phrase not in the Act (0 hits in either extraction) | **High** |
| S11(2) | carve-out applies to sharing "in compliance with … any other law … pursuant to any receipt of a request" | only to a Data Fiduciary "**authorised by law to obtain such personal data**, where such sharing is pursuant to a request **made in writing**" | **High** (database version is broader) |
| S12(3) | adds a duty to make the Data Processor erase too | s.12(3) has no Data Processor clause (that duty is in s.8(7)(b)). The database also drops "make a request in such manner as may be prescribed" | Medium-high |
| S19(3) | expertise in laws related to "**data protection**"; "not less than the **prescribed period**" | "laws related to **social or consumer protection**"; no minimum period | **High** |
| S22(3) | cooling-off only for organisations that were party to Board proceedings, plus a proviso exempting government jobs and "clause (45) of section 2 of the **Companies Act, 2013**" | "shall not … except with the previous approval of the Central Government, accept **any employment**, and shall also disclose … subsequent acceptance of employment with any Data Fiduciary against whom proceedings were initiated". **No proviso; no Companies Act anywhere in the Act** | **High** (a made-up proviso, same kind of error as S28) |
| S29(8) | Tribunal exercises "the same jurisdiction … as … under Section 18 of the TRAI Act" | "Without prejudice to … **section 14A and section 16** of the TRAI Act … in accordance with such procedure as may be prescribed" | **High** |
| S29(9) | appeal "in accordance with **section 18B** of the TRAI Act" | "the provisions of **section 18** of the TRAI Act … shall apply". "18B" isn't in the Act | **High** (wrong citation) |
| S32(2) | undertaking may include "**to make good the loss** caused to any Data Principal" | Not in the Act (0 hits) | **High** (made-up) |
| S37 | blocking "in such manner as provided in **sub-section (2) of section 69A** of the IT Act"; blocks the "computer resource" | No s.69A reference (0 hits). The Act blocks "any **information** … in any computer resource"; the Board's reference must be "in writing" and "advises" blocking; the direction can go to "any agency … **or any intermediary**" | **High** |
| S40(2) | 24 rule-making items, with cross-references to "clause (b) of sub-section (1) of section 28" and "sub-clause (e) of clause (7) of section 28" | 26 items, (a)–(z). Neither cross-reference exists; item "(y) the procedure for dealing an appeal under sub-section (8) of section 29" is missing | **High** (for a tracker that maps Rules back to the Act) |
| S9(5) | safe-harbour for a "Data Fiduciary **or class of Data Fiduciaries**", "having regard to such factors…" | "if satisfied that **a Data Fiduciary** has ensured … verifiably safe, notify … the age above which **that Data Fiduciary** shall be exempt" | Medium-high |
| S27(1)(b),(c),(2),(3) | (b) covers "Data Fiduciary **or Data Processor**"; (c) any complaint against a Consent Manager; (2) adds "after making such inquiry as may be prescribed"; (3) adds State Government references and a hearing | (b) Data Fiduciary only; (c) "a complaint made by a Data Principal … in relation to her personal data"; (2)/(3) have none of those additions | Medium-high |
| S6(10) | "In the event of any dispute … burden of proof … shall lie on the Data Fiduciary" | "Where a consent … is the basis of processing … and a question arises … in a proceeding, the Data Fiduciary shall be obliged to prove…" Same effect, but not the Act's words | Medium |
| S6(4),(6),(7),(8) | (4) drops "Where consent … is the basis of processing"; (6) quietly changes the Act's own cross-reference "under sub-section (5)" to "(4)"; (7) drops "give"; (8) drops "in such manner and subject to such obligations as may be prescribed" | quotes in the side-by-side file | Medium |
| S8(11) | adds "over telephone … letter … **initiating any proceeding** under any law" | "in person or by way of communication in electronic or physical form" | Medium |
| S5(2) | turns clause (b) into a "Provided that…" proviso | (2)(a)/(b) clauses, no proviso; notice covers what "has been processed" | Medium |
| S11(1), S12(1) | drop "including consent as referred to in clause (a) of section 7"; S12(1) says "in the manner as may be prescribed" | Act: "in accordance with any requirement or procedure **under any law** for the time being in force" | Medium |
| S21(1)(b) | "convicted of an offence which involves moral turpitude" | "which **in the opinion of the Central Government**, involves moral turpitude" | Medium |
| S23(1),(3) | (1) orders "authenticated by the **signature of the Chairperson**…"; (3) senior Member presides only at meetings | (1) "authenticate its orders, directions and instruments in such manner as may be prescribed" (no "signature of the Chairperson" in the Act); (3) covers absence, illness "or any other cause" | Medium |
| S32(5), S39, S43 | S32(5) adds "as if the undertaking had not been accepted"; S39 adds "or the Appellate Tribunal"; S43 merges the Act's (2) into a proviso, so the database's "(2)" is really the Act's (3) | as stated | Low-medium |
| S3, S16(2), S18(1), S20(2); S20–S23 | S3's illustration is reworded but shown as the Act's own; small additions; "he/his" throughout S20–S23 | The Act uses "she/her" on purpose (s.2(y)) | Low |

**Summary: 12 rows have at least one high-risk statement** (S6.1_8_10, S8, S9, S11, S12, S19, S22, S27.1a_c_e_2_3, S29, S32, S37, S40). 5 more have medium issues only, and 4 have low ones only. **Most rows are also shortened** (illustrations, Explanations and "or the rules made thereunder" dropped).

---

## 3. Rules table (never checked before): mostly exact, with 3 gaps

I did a mechanical comparison of all 31 rows against the English half of the Rules PDF (pages 24–41). Results are in `rules_mechanical_diff.txt`.

- **All 23 Rules are verbatim.** After tidying up spacing and quote marks, **none** of the database text is missing from the PDF. The only differences are headings and "Illustration" labels. This is good news, and the opposite of the Act table.
- **Gap 1: the corrigendum (1.3) was never applied.** R1(3), R1(4), R13(5) and R23(1) hold the uncorrected text. Draft ready.
- **Gap 2: some parts of the Schedules were left out.**
  - The First Schedule's Note is missing. It defines "body corporate", "control", **"net worth"** (which the ₹2 crore condition depends on) and "promoter".
  - The First Schedule Part B illustration (the P/B1/B2 consent-routing cases) is missing.
  - The Fourth Schedule's Note is missing: all the healthcare and education definitions the exemptions rely on.
  - The Fifth and Sixth Schedules lost their paragraph headings ("Salary", "Leave", and so on); the text itself is intact.
- **Gap 3: the Third Schedule is paraphrased, not verbatim.** Rows 2–3 say "Same exceptions as above / Same three-year rule as above". That's accurate in substance, but it's the only Rules row that isn't word-for-word.
- **Two more wording oddities that the corrigendum did *not* fix.** Keep the database verbatim, but EY legal may want to know:
  - Rule 13(5) names the "Ministry of Electronics and **Technology**" (missing "Information"). The Hindi text omits "सूचना" too.
  - Rule 14(3) reads "shall prominently publish … within a reasonable period not exceeding ninety days under its grievance redressal system…". It has no object ("publish *what*").
  - The preamble also says "section 40 of the of the".
- **Rules summaries:** all checked against the text. Only R12 is wrong (see 1.7).

---

## 4. The Act PDF "max_tokens" failure: a new explanation, and why "fixing" it the obvious way would be dangerous

*"max_tokens" means the AI hit its maximum reply length and was cut off mid-answer.*

### 4.1 The earlier test couldn't have seen the answer being written

Anthropic's docs say that without fine-grained tool streaming:

> "the API buffers and validates each parameter value before streaming it back, so nothing prints for a large parameter until Claude has finished generating it" ([source](https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming))

The streaming docs add that "Current models only support emitting one complete key and value property from `input` at a time" ([source](https://platform.claude.com/docs/en/build-with-claude/streaming)).

`report_changes` has exactly **one** top-level parameter, `changes`. So the whole answer is one parameter. If it's cut off by max_tokens before it finishes, the stream shows one empty piece of text followed by max_tokens. That is exactly what was observed.

So the observation doesn't show the model wrote nothing. **It's equally consistent with the model writing a very long `changes` list.** The original "too many differences" theory was ruled out on evidence that couldn't tell the two apart.

### 4.2 Why a very long answer is expected here

We now know nearly every Act row differs from the PDF (§2). The prompt tells the model to report any "Correction" or "Clarification", to set `old_full_text` to the database text (up to 2,000 characters per row) and `new_full_text` to the PDF wording. Doing that honestly for dozens of rows needs far more than 16,000 output tokens.

The Rules "work" for the opposite reason: the model only sees Hindi (1.4), so it has nothing to compare and correctly reports nothing.

### 4.3 How to confirm it: one call, about $0.05, not run

`diagnose_act_pdf_eager_stream.py` re-runs the exact production prompt once with `eager_input_streaming: true`. This makes the API stream the answer as it's written, so you can see how far it got. It prints the partial answer, how many provisions it listed, and which change types it used.

### 4.4 Why raising max_tokens until it "succeeds" would be worse than failing

If the call succeeds, `apply_change.py` would **automatically write dozens of AI-written "Corrections" into the master text**, mark them "Approved" by "auto", and move `latest_change_id`. The Word document would then show all of them as government amendments.

There are two more problems in `apply_change.py`:

- It **replaces the entire `full_text` with `new_full_text`**, which the prompt describes as only "the verbatim new clause text". So an amendment to one sub-clause would wipe out the rest of the section. My test on a copy did exactly that.
- It overwrites `current_summary` with a one-line "what changed" description.

### 4.5 Recommended fix (a design change for you to decide on)

**Compare the text yourself first, and only send the AI what changed.**

1. Store the extracted text from each run.
2. When the fingerprint changes, compare old and new text in plain Python.
3. Send the model only the changed passages and the matching provisions.

This fixes, in one go: the empty-output failure, the 60,000-character cut-off, the Hindi-first problem, the noise from paraphrased rows, and most of the cost.

Also:

- Pin `pypdf` to one version. The same Act PDF gives a different fingerprint under pypdf 3.17.4 (`78fe34df…`) than under 6.19.0 (`f15bda1f…`, the one your database holds). An unpinned upgrade (`pypdf>=4.0`) could flag every source as "changed" overnight.
- Add real sources for new notifications, such as the eGazette search results for MeitY, or MeitY's DPDP page listing.

---

## 5. Pipeline code: other findings

| Where | Finding | Status |
|---|---|---|
| `run_pipeline.py` + `fetch_sources.py` | **A change is lost for good after one failed day.** The new fingerprint is saved *before* the AI checks the change. If the AI call fails, the next run sees matching fingerprints, reports "No Change Detected", and never looks again. You get one error email, then silence. | Draft fix, tested: the old fingerprint is put back when the AI call fails, so the next run retries |
| `fetch_sources.py` | **Download failures are still silent on the fixed branch.** The row is marked Error, but `run_pipeline` never hears about it: exit code 0, and the email says "No changes". This is what happened in production on 18–19 Sep. The fingerprint is also blanked, so the next successful download looks like a "change". | Draft fix, tested: download errors are reported and the last good fingerprint is kept |
| `apply_change.py` | Whole `full_text` overwritten by a clause excerpt; summary replaced by a change description; new provisions get `review_status='Confirmed'` by `'auto'`, `effective_date = today`, and `reference = <summary sentence>`; `old_full_text` is never checked against the database; `effective_date` isn't updated when something is amended | Needs your decision |
| `'Correction'` change type | Means both "the government issued a corrigendum" (from the AI) and "our data was wrong" (your manual fixes tonight). Only `latest_change_id` tells them apart. | Suggest a separate `origin` column, or a distinct type such as `'Data Fix'` |
| `notify.py` | On error days the email body still starts "No changes were detected across PIB, MeitY, or eGazette today" | Low |
| Uncommitted `SYSTEM_PROMPT` edit | Confirmed: the only difference from HEAD is the removed block of old OpenRouter instructions ("Respond with ONLY a JSON object…"). **Recommend committing** it as cleanup: that block contradicts the forced tool use, and it's already proven harmless. | Your call |

---

## 6. GitHub Actions and deployment

- **Late runs.** Commit times on `main` are 04:55–05:23 UTC, but the job only takes 49 seconds to 5 minutes 20 seconds. So the ~4.5-hour delay happens **before the job starts**, while it waits in GitHub's queue. It isn't the script being slow. I can't find the root cause from outside GitHub; its scheduler makes no timing guarantee. Options:
  - accept it (the pipeline doesn't depend on the time of day);
  - move the schedule off the busy :00/:30 marks (for example `17 23 * * *`);
  - start it from an outside scheduler.
- **Secrets.** I can't see repository secrets. The Claude code path has **never run on GitHub**: the only branch run, #1 on 14 Sep, came before the switch to Claude. Before merging, add the `ANTHROPIC_API_KEY` secret (and optionally a `CLAUDE_MODEL` variable), then trigger one manual run on the branch.
- **Merge conflicts to expect:**
  - `db/dpdpa.db` is a binary file changed on both sides. Keep the **branch** version; `main`'s daily commits only change `source_log` fingerprints and dates.
  - `daily-check.yml`: keep `main`'s `checkout@v5`/`setup-python@v6` together with the branch's settings.
  - Also check the change IDs: a production change would take `CHG-0033`, which the branch already uses.

---

## 7. Repo tidy-up (working copy vs `fd476a7`)

| File | State | Recommendation |
|---|---|---|
| `src/classify_change.py` | modified (SYSTEM_PROMPT cleanup only) | commit |
| `docs/DPDP_Rules_2025.docx` | modified, but **the text is identical** to HEAD (only the file's internal packaging changed) | revert (`git checkout -- docs/DPDP_Rules_2025.docx`) |
| `pipeline-architecture-flow.html` | modified: now says cron `30 0 * * *` is "04:30 UTC / 10:00 IST", which is wrong (`30 0` means 00:30 UTC) | revert, or reword as "scheduled 06:00 IST; usually runs about 10:30 IST because of GitHub queueing" |
| `README.md` | still describes OpenRouter | update when merging |
| `graphify-out/converted/DPDP_Act_2023_*.md` | still contains the pre-correction Act text ("Benches" and so on) | regenerate or delete, so no tool reads it as reference |
| `data/~$DPDP_Rules_Tracker.xlsx` | leftover Excel lock file from 31 Aug (ignored by git) | harmless |
| `fd476a7` | already pushed to origin, although the night-2 log said "don't push" | no action; just noting it |

---

## 8. Design question: condensed wording vs "verbatim is a firm requirement"

**My finding: this is drift from the original intent, not a deliberate choice.** The evidence:

- `README.md` says: "including the verbatim clause text (`provisions.full_text` — no paraphrasing, no abridging)".
- `db/schema.sql` says: `full_text -- verbatim clause text`.
- `seed_dpdp_act_full.py` itself prints "Loaded {n} Act provisions **(verbatim)**".
- The Rules seed promises "verbatim … no paraphrasing or abridging" and **delivers** it (§3).
- The only row that openly declares it's shortened is S2 (a subset of the definitions). Tonight's audit took that one row as proof that shortening was "by design" for all 44 sections. I don't think it shows that.
- The older `docs/full_text/DPDPA-S*.md` files (31 Aug) are openly paraphrased *and* correct in substance (for example S26 has no "Benches", and S42 has the doubling cap). The seed text, written about an hour later, is neither verbatim nor consistent with them.

**Options for you:**

- **(a) Rebuild all 48 Act rows word-for-word from the PDF.** A mechanical draft of every row is ready in `act_verbatim_draft.json`. The Schedule table needs rebuilding by hand, and each row still needs a human read-through.
- **(b) Keep the condensed version,** but label it as a paraphrase everywhere (README, schema, Excel README, Word subtitle) and stop the classifier comparing it word for word.
- **(c) Recommended: a mix.** Word-for-word `full_text` (option a), with plain-language wording kept in `current_summary`.

---

## Decisions I need from you

1. Apply the `export_word.py` fix and regenerate the Act document? (Recommended, before any demo.)
2. Merge the branch to `main` now, or keep production on old code until the Act table is decided?
3. G.S.R. 892(E): highlight it as a regulatory change, or not? Then run the draft script.
4. The 5 summary fixes: approve as drafted?
5. Act table: option (a), (b) or (c) from §8?
6. Spend about $0.05 on the §4.3 diagnostic, or go straight to the "compare text first" redesign?
7. Working copy: commit the SYSTEM_PROMPT cleanup, revert the Rules docx and the HTML edit?

All drafts are in `docs/audit_2026-09-23/` on your computer:

- `draft_code_fixes.patch`
- `DRAFT_apply_audit_fixes_2026-09-23.py`
- `diagnose_act_pdf_eager_stream.py`
- `act_verbatim_draft.json`
- the side-by-side comparison files
