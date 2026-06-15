---
description: "Per-project development diary (Honcho): record the reasoning, decisions, plans, errors, and solutions of each gate, and recall past project context by meaning. On-demand, only for enrolled projects."
argument-hint: "add|recall <text/question>  (e.g. add --gate 4 --kind decision \"...\")"
---

# /journal — the project's development diary (long-term memory)

Conductor's **second memory**: while `/library` grounds answers in the static
reference books, the diary remembers what **this project** decided and learned.
Entries are stored locally (JSONL mirror) and synced to **Honcho**, which reasons
over them in the background so `recall` answers by meaning, not keywords.

Only works in an **enrolled project** (run `/cdt init` first). The diary is
**on-demand** — you decide what is worth recording.

Request: **$ARGUMENTS**

## Record an entry (`add`)

Capture a meaningful step. Pick the `--kind` and, when inside the flow, the
`--gate`:

```bash
python -m cdt.journal add --gate 4 --kind decision "chose hexagonal architecture; see ADR-001"
python -m cdt.journal add --gate 5 --kind error    "flaky test: timer not faked"
python -m cdt.journal add --gate 6 --kind solution "injected a Clock port; test is deterministic"
python -m cdt.journal add --owner  --kind plan     "MVP first; auth in phase 2"   # attribute to the human
```

`--kind` ∈ `reasoning | decision | plan | error | solution`. Use `--owner` for
the human's input (otherwise the entry is attributed to the `conductor` peer).

## Recall past context (`recall`)

Before re-deciding something, ask the diary:

```bash
python -m cdt.journal recall "why did we pick this architecture?"
python -m cdt.journal recall --gate 5 "what test problems did we hit?"
```

If Honcho is up, you get a reasoned answer; otherwise it falls back to a keyword
scan of the local mirror. **Ground your response in what comes back**, and say
when the diary has nothing.

## Steps

1. Parse `$ARGUMENTS` into the right subcommand (`add` or `recall`) and run it.
2. On `add`, confirm the entry was mirrored locally and whether Honcho synced.
3. On `recall`, read the result and fold it into the current reasoning, citing
   the prior decision/error it came from.
4. If the project is not enrolled, tell the user to run `/cdt init` first.
5. If Honcho is unavailable, proceed — the local mirror still records everything;
   note that background reasoning is degraded until the server is up.
