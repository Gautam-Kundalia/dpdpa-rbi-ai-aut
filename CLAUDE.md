# CLAUDE.md — read this first, every session

This repo is the **DPDP regulatory-change tracker** (daily pipeline in `src/`,
running in production on GitHub Actions) and is **mid-way through being
extended into a multi-client DPDP compliance platform** (FastAPI backend +
Next.js frontend + SQLite + OpenRouter).

## Before doing anything

1. Read `platform/CHECKPOINT.md` — what is done, what is next, open decisions.
2. Read `platform/SPEC.md` — the design you must build to. Do not redesign it;
   if something in it is wrong or impossible, record it under
   "Spec change requests" in `CHECKPOINT.md` and pick the smallest safe option.
3. Do only the session you were asked to do (`platform/prompts/SESSION_XX.md`),
   or, if given `platform/prompts/RESUME.md`, the "Next action" in the checkpoint.

## Who you are working for

Gautam Kundalia (Associate Consultant, EY). He is not a full-time developer.
**Explain everything you did in plain, simple words and define any technical
or management jargon** the first time you use it — in chat, in `CHANGELOG.md`
and in the checkpoint's session log.

## Hard rules (these have all caused real problems before)

- **Production is live.** `main` runs `.github/workflows/daily-check.yml` every
  day, and the bot commits `db/dpdpa.db`, `docs/*.docx` and `data/*.xlsx` back to
  `main`. Never break `src/` or the existing tests. Run `python -m pytest` before
  every commit.
- **Branching:** Session 1 part A (the interim approval fix) is the only work
  that goes to `main`, and only after Gautam says OK to push. All platform work
  happens on the branch `platform-build`. Never merge `platform-build` into
  `main`, never force-push, never rewrite history.
- **Never edit or commit `db/dpdpa.db`, `docs/*.docx` or `data/*.xlsx` on
  `platform-build`.** The platform uses its own dev copies under `var/`
  (git-ignored). This keeps the future merge conflict-free.
- **No silent failures.** Never catch an exception and carry on as if nothing
  happened (that was "Bug A" in Sept 2026). Errors must be raised, logged, or
  shown to the user.
- **Verbatim legal text.** Never paraphrase or "tidy" text in `provisions.full_text`.
  Any AI output that claims to quote a law or a client document must be checked
  in code to exist word-for-word, or it is rejected.
- **No real client data.** Use only the fictional test client in
  `backend/tests/fixtures/`. Never commit anything that looks like a real
  client's document.
- **AI spend:** tests always use the mock LLM. Real AI calls only when a session
  file explicitly allows it, within the stated dollar cap, and the cost goes in
  the checkpoint's session log.
- **A data correction must never change what the documents show as a change in
  the law.** `change_origin='regulatory'` means the government did something;
  `change_origin='data_correction'` means we fixed our own typing. Only the
  first is ever highlighted or reported. Fixing our own mistake must not add,
  remove or move a single highlight. (This was audit finding H-6: a correction
  applied after a real amendment silently erased that amendment's highlighting.)
- **A "regulatory" record is anything the government did, however we found it.**
  It does not matter whether the pipeline detected it or a person typed it in
  from a Gazette PDF by hand. If the government changed the law, the row is
  `regulatory`. (Audit finding H-5: two items of a government corrigendum were
  filed as our own data correction because a human had applied them.)
- **Every one-off data script is a dry run by default.** No `--apply`, no
  writes. It must print before-and-after for everything it would touch, refuse
  to write if its own checks fail, be safe to run twice, and take `--db` so it
  can be rehearsed on a copy. Prove it on a copy; never run it on `db/dpdpa.db`.
- **A test that cannot fail is not a test.** Before trusting one, put the old
  behaviour back and watch it go red. A test that re-implements the code's own
  query and then checks that answer is checking itself. (This is what let audit
  findings C-1 and M-5 survive a green test suite.)
- **Things only Gautam does:** pushing to `main`, merging, adding/changing GitHub
  secrets, deploying to any server, sending anything to a real client, publishing
  obligations for real use (needs EY legal sign-off). Prepare these; don't do them.

## This machine (Gautam's Windows PC)

- A virtual environment exists at `.venv/` — activate it (`.venv\Scripts\activate`)
  or call `.venv\Scripts\python` so installs don't go into the system Python.
- Windows Device Guard blocks `pip.exe` directly — always use `python -m pip`.
- PyMuPDF **does** work on this PC. It is installed as version 1.28.2, and both
  `import pymupdf` and `import fitz` succeed (`fitz` prints a deprecation
  warning — use `import pymupdf`). An earlier note here said it could not load
  because of a blocked DLL; that was true once and is no longer. Checked again
  on 30 Sep 2026 (audit finding L-7). `pypdf` and `pdfplumber` are installed
  too, and the verbatim guard deliberately uses two independent extractors.
- No `gh` CLI and no GitHub token on this PC — you cannot open PRs or read
  secrets. Write a PR description file instead when a session asks for one.
- The Next.js work needs Node.js 20+ (`node -v`). If it is missing, stop and tell
  Gautam how to install it — don't try to work around it.

## Logging discipline (Gautam's standing request)

After every completed task: tick it in `platform/CHECKPOINT.md` and set its
"Next action". At the end of every session: add a plain-language entry to
`CHANGELOG.md` and a row in the checkpoint's session log. If your context is
getting full, stop at a clean point, update the checkpoint, commit, and tell
Gautam to start a new session with `platform/prompts/RESUME.md`.
