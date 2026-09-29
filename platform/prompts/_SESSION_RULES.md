# Rules for every build session (read with the session file)

## Start of session
1. Read `CLAUDE.md`, `platform/SPEC.md`, `platform/CHECKPOINT.md`.
2. Run `git status` and `git branch --show-current`. If there are uncommitted
   changes you didn't expect, stop and ask Gautam what they are — do not discard them.
3. Check the checkpoint: every task of the previous session should be `[x]`.
   If not, finish those first (they are the "Next action"), then start this session.
4. Switch to the branch the session file names; `git pull` it if it exists on the remote.
5. Run the existing test suite once (`python -m pytest -q`, plus `backend` tests
   once they exist) so you know the starting state. Record failures before touching anything.
6. Update the checkpoint: "Current session: N (in progress)".

## While working
- Work through the session's tasks **in order**. After each task: tests green →
  tick it in the checkpoint → update "Next action" → commit with a clear message
  (end commit messages with the attribution lines your environment requires).
- Small commits beat one big commit. Never commit `var/`, `.env`, `db/dpdpa.db`,
  `docs/*.docx`, `data/*.xlsx` on `platform-build`.
- If something in SPEC.md doesn't work in practice, pick the smallest safe
  option, add a row to "Spec change requests" and carry on.
- If a task needs a decision only Gautam can make and nothing sensible is
  reversible, mark it `[!]`, add it to Blockers, and move to the next task.
- **Context budget:** if the conversation is getting long (you have read many
  large files or done most of the tasks), stop at a clean point: commit, update
  the checkpoint's "Next action" with exact file names and what's left, and tell
  Gautam to start a fresh session with `platform/prompts/RESUME.md`. Stopping
  cleanly is always better than running out mid-edit.
- Tests use the mock LLM. Real AI calls only if the session file allows it,
  within its cap; log the spend.

## End of session
1. All tests green (`python -m pytest -q` at repo root and in `backend/`;
   `npm run lint && npm run build` in `frontend/` once it exists).
2. Checkpoint: tick tasks, set "Current session" to done, set "Next action" to
   the next session's prompt file, add a session-log row (plain words, tests,
   commits, AI spend).
3. `CHANGELOG.md`: a dated, plain-language entry — what was built, why, what
   Gautam needs to do (if anything), cost. Define any jargon.
4. Commit, then `git push origin platform-build` (never push `main` unless the
   session file says so and Gautam said OK).
5. Final chat message to Gautam, in simple words: what now works, how he can
   see it (exact commands), anything he must decide or do, and the exact prompt
   to paste for the next session.
