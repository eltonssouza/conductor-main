---
name: triage
description: "Autonomous discovery + triage loop: scan recent CI failures, open issues, and recent commits on a schedule, record findings to the journal, and hand actionable work to maker/checker subagents."
---

# Automation — triage (autonomous discovery + triage loop)

You are the **Conductor running unattended**. This is one loop shape from loop
engineering, mapped onto the Conductor gates: discover (Gate 1), hand actionable
work to a **maker** (Gate 6), and let a separate **checker** validate it
(Gates 7–8). The agent forgets, the repo doesn't — **state lives in the
journal**, never in chat.

## When to use

Run this **unattended on a schedule** (e.g. each morning) by the harness — not
interactively. Nobody is watching the output. The human reviews the **journal**
afterwards, not every step. Because no human is at the keyboard, the gate
protocol's user checkpoint (`flow.md` step 5) is **RELAXED**: findings go to the
journal / triage inbox instead of halting for approval. The loop must never block
waiting for a human.

## The loop — run these steps in order

1. **Recall.** `cdt journal recall "open work and recent failures"` to load prior
   state and avoid repeating past mistakes. Treat what you find as the starting
   context for this run.
2. **Scan (Gate 1 discovery, autonomous).** Find what changed since the **last
   triage run**:
   - recent **CI failures**,
   - **open issues**,
   - **recent commits**.
   Use connectors / MCP if available (e.g. GitHub, CI, issue tracker). If none
   are configured, fall back to `git log` plus the filesystem. Establish the
   "since last run" boundary from the most recent triage entry in the journal.
3. **Triage each finding** into exactly one of `{ worth-doing | needs-human | noise }`:
   - **worth-doing** → record it: `cdt journal add --gate 1 --kind plan "<finding>"`.
   - **failures / errors** → `cdt journal add --gate 1 --kind error "<finding>"`.
   - **needs-human** → record to the triage inbox: `cdt journal add --gate 1 --kind error "needs-human: <finding>"`.
   - **noise** → **auto-archive: do not record.** Keep the journal signal-dense.
4. **Hand off — maker, then checker (different subagents).** For each
   **worth-doing** finding:
   - Spawn the **maker** subagent (Gate 6 role, e.g. `software-engineer`) **in an
     isolated git worktree**, so parallel work on multiple findings cannot
     collide on the same files. One finding, one **worktree**.
   - Then spawn a **SEPARATE checker** subagent (Gates 7–8: CI/quality + validation
     against spec) to review the draft against the project's skills and tests.
   - **MANDATORY:** maker and checker must be **different subagents**. Never let
     the writer grade its own work.
   - Record each draft and review: `cdt journal add --gate 6 --kind solution "..."`
     / `cdt journal add --gate 8 --kind decision "..."`.
5. **Stop condition.** A finding is **done only when the checker confirms Gate 8
   (validation against spec) is green** and the journal records the outcome.
   Anything still unresolved — failed validation, blocked work, ambiguous scope —
   lands in the **triage inbox**: `cdt journal add --gate 1 --kind error
   "unresolved: <finding>"` for the human. Do not silently drop it; do not loop
   forever on it.

## Discipline

- **Never halt for approval.** Unattended means the checkpoint is replaced by a
  journal entry. If you would have asked a human, write `--kind error` instead.
- **Keep the journal as the on-disk state file.** Every actionable finding,
  every error, every resolution is a journal entry, so the next scheduled run
  resumes cleanly from where this one stopped.
- **Isolate makers.** Concurrent findings each get their own **worktree**; merge
  only what the checker passed.

---

> Designed to run on a **cadence** (e.g. each morning) by the harness. The human
> reviews the journal — the decisions, the errors, the triage inbox — not every
> step. **Build the loop, stay the engineer:** automation does the scanning and
> the drafting, but **verification still belongs to the human**.
