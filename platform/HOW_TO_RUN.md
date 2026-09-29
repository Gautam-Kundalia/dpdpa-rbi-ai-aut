# How to run the platform build with Claude Code (for Gautam)

The build is split into **8 Claude Code sessions**. Each one is small enough to
fit in one Claude Code conversation. Between sessions, Claude Code keeps its
place in `platform/CHECKPOINT.md`: a to-do list it ticks after every task, plus
a "Next action" line and a log of what happened. So you can close Claude Code at
any time and pick up later.

## Files in this folder

| File | What it is |
|---|---|
| `SPEC.md` | The design Claude Code builds to (architecture, databases, approval flow, KPIs) |
| `CHECKPOINT.md` | The live progress tracker — **open this to see where things stand** |
| `prompts/_SESSION_RULES.md` | Rules every session follows (start, commit, stop, wrap-up) |
| `prompts/SESSION_01.md` … `SESSION_08.md` | The detailed instructions for each session |
| `prompts/RESUME.md` | Use when a session stopped before finishing |
| `../CLAUDE.md` (repo root) | Claude Code reads this automatically at the start of every session |

## Each time

1. Open a terminal in `C:\Users\ASUS\dpdpa-rbi-ai-aut`.
2. Start Claude Code: `claude`
3. Paste the prompt for the session (below). Let it work; answer if it asks.
4. When it finishes, it tells you what changed, how to check it, and the next
   prompt. Glance at `platform/CHECKPOINT.md` to confirm.
5. **Start a fresh Claude Code conversation for each session** (type `/clear`
   or quit and run `claude` again) so it has a full context window.

If a session stops part-way (context full, error, you closed it): start a fresh
conversation and paste the **Resume** prompt. It works out where it was from the
checkpoint and git history.

## The prompts to paste

**Session 1**
```
Read CLAUDE.md, platform/SPEC.md, platform/CHECKPOINT.md and platform/prompts/_SESSION_RULES.md, then carry out platform/prompts/SESSION_01.md exactly. Explain what you did in plain words at the end.
```

**Sessions 2–8** — same prompt, change the number:
```
Read CLAUDE.md, platform/SPEC.md, platform/CHECKPOINT.md and platform/prompts/_SESSION_RULES.md, then carry out platform/prompts/SESSION_0N.md exactly. Explain what you did in plain words at the end.
```

**Resume (any time a session didn't finish)**
```
Read CLAUDE.md and carry out platform/prompts/RESUME.md.
```

## What each session delivers

| # | You will have after it | Roughly needs from you |
|---|---|---|
| 1 | A working **Approve changes** button on GitHub (fixes the "approvals keep coming back" problem today), a read-only Excel, and the start of the new backend | Say OK before it pushes to `main` |
| 2 | Logins and roles, the real approval flow via the backend, OpenRouter support | Optional: OpenRouter key in `.env` |
| 3 | A draft **obligations checklist** from the 79 provisions, with a coverage report for EY legal | OpenRouter key in `.env` (spend cap $2) |
| 4 | Client spaces, the questionnaire, document upload and search, a fictional test client | Nothing |
| 5 | The AI mapping engine with quote-checking, consultant review, re-checks after law changes, an accuracy report | Spend cap $1 |
| 6 | The web app: login + EY admin console | Node.js 20+ installed |
| 7 | The client dashboard with all KPIs and a board-pack export | Nothing |
| 8 | Security review, backups, Docker files, CI, a full rehearsal with a pretend law change, the runbook | Nothing |

Expect some sessions to need one extra **Resume** run — that is normal, not a failure.

## Things only you (or EY) can do — Claude Code will prepare, not do, these

- Push to `main` / merge `platform-build` into `main`.
- Add secrets (e.g. `OPENROUTER_API_KEY` to your local `.env`; GitHub secrets later).
- Decide the open questions in the checkpoint (D1–D7): approval model, hosting
  (EY IT), client data + AI (EY Risk), obligations sign-off (EY legal), baseline
  confirm, commencement date, which AI provider the daily monitor uses.
- Deploy to a server and do the cutover (the runbook written in Session 8 walks you through it).

## Safety built into the prompts

- Production (the daily GitHub run on `main`) is never touched except the small
  Session 1 fix, which waits for your OK.
- All new work lives on the `platform-build` branch and in a git-ignored `var/`
  folder, so the live database and reports are never edited by the build.
- Only a fictional test company is used; no real client documents.
- Every AI call is capped in dollars and logged.
