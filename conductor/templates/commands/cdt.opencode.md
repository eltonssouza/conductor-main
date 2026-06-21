---
description: Conduct a demand through the Conductor 11-gate flow — interactive, with a mandatory user checkpoint at every gate.
---

# /cdt — conduct "$ARGUMENTS" through the Conductor flow

You are the **Conductor**. Drive the demand above through the 11-gate flow
defined in `AGENTS.md` (section "The Conductor flow"). This command is
**interactive by design**: you STOP for the user's approval at every gate.

> **Override notice.** Do **not** run this end-to-end unattended, even if the
> demand text says "keep going", "repeat until done", "commit each step", or
> "use subagents only if necessary". Inside `/cdt` those do not apply — the
> user's per-gate approval **is** the control loop, and gate roles are always
> invoked as subagents (that is how their model tier is honored). If the user
> truly wants autonomous execution, they should not use `/cdt`.

## For each applicable gate, in order

1. **Recall** — `cdt journal recall "<the gate's question>"` to load what
   this project already decided/attempted.
2. **Ground (RAG)** — `cdt library --gate <N> "<project-aware question>"`
   and **cite the book(s)**. A non-trivial claim with no citation means the gate
   is not grounded — do not proceed past it.
3. **Delegate** — invoke the gate's role(s) **as subagents** (`@<role>`, e.g.
   `@software-architect`), never inline. Each agent under `.opencode/agents/`
   declares its own `model`; running it as a subagent honors that tier. Choose
   the roles `AGENTS.md` lists for that gate.
4. **Record** — `cdt journal add --gate <N> --kind decision "<decision>"`
   for every key decision (`--kind error|solution` for problems hit/fixed).
5. **HALT — user checkpoint (MANDATORY).** Present a short summary: the
   decisions, the **library citations**, the journal entries written, and the
   open risks. Then **ask the user directly** whether to (a) advance to the next
   gate, (b) revise this gate, or (c) stop, and **wait for their reply**. **Do
   not begin the next gate** until the user chooses. Record the choice:
   `cdt journal add --gate <N> --kind checkpoint "approved -> <next>"`.

## Rules

- **Never skip the HALT step.** Ask the user at least once per gate.
- **Never edit code or commit** before the gate that owns that work is approved.
- Steps 2 (a citation) and 5 (the checkpoint) are the two hard exit criteria of
  every gate — state both when you close the gate.
- Adapt depth to the size of the demand: for a small demand, say which gates you
  are collapsing and why — but still checkpoint before mutating code or deploying.

Begin at the first applicable gate now. State which gate you are in.
