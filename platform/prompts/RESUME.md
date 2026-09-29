# Resume prompt — use when a session stopped part-way

You are continuing the DPDP Compliance Platform build in this repo.

1. Read `CLAUDE.md`, `platform/SPEC.md`, `platform/CHECKPOINT.md` and
   `platform/prompts/_SESSION_RULES.md`.
2. In the checkpoint, find "Current session" and "Next action". Open the matching
   `platform/prompts/SESSION_XX.md` and read the task(s) that are `[ ]` or `[~]`.
3. Check the real state before trusting the checkpoint: `git status`,
   `git log --oneline -15`, and run the tests. If code for a `[~]` task exists
   but is incomplete or failing, finish it; if the checkpoint says `[x]` but the
   code/tests disagree, fix it and note the discrepancy in the session log.
4. Continue from the next unfinished task of that session only, following the
   rules file (tests → tick → commit after every task; stop cleanly if context
   runs low).
5. When that session's tasks are all `[x]`, do its wrap-up and tell Gautam the
   exact prompt for the next session.
