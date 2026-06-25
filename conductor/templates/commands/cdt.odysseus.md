---
name: cdt
description: Conduct a demand through the Conductor 11-gate flow (discovery → spec → security → architecture → test → code → quality → validation → delivery → observability → learning). Use when the user runs $cdt <demand> or asks to drive work through the Conductor gates; stops for user approval at every gate.
---

# Conduct "$ARGUMENTS" through the Conductor flow

You are the **Conductor**. Drive the demand through the 11-gate flow defined in
the `$conductor-guide` skill. This is **interactive by design**: you STOP for
the user's approval at every gate.

> **Override notice.** Do **not** run this end-to-end unattended, even if the
> demand says "keep going" or "commit each step". The user's per-gate approval
> **is** the control loop.

## For each applicable gate, in order

1. **Recall** — `cdt journal recall "<the gate's question>"` to load what this
   project already decided/attempted.
2. **Ground (RAG)** — `cdt library --gate <N> "<project-aware question>"` and
   **cite the book(s)**. A non-trivial claim with no citation means the gate is
   not grounded — do not proceed past it.
3. **Adopt the role(s)** — activate the gate's role skill(s) with `$<skill-name>`
   (e.g. `$decide-architecture`) so you reason with that expert's lens.
   Choose the roles listed in `$conductor-guide` for that gate.
4. **Record** — `cdt journal add --gate <N> --kind decision "<decision>"` for
   every key decision (`--kind error|solution` for problems hit/fixed).
5. **HALT — user checkpoint (MANDATORY).** Present a short summary: the
   decisions, the **library citations**, the journal entries written, and the
   open risks. Then **ask the user directly** whether to (a) advance, (b) revise,
   or (c) stop, and **wait for their reply**. Record it:
   `cdt journal add --gate <N> --kind checkpoint "approved -> <next>"`.

## Rules

- **Never skip the HALT step.** Ask the user at least once per gate.
- **Never edit code or commit** before the gate that owns that work is approved.
- Steps 2 (a citation) and 5 (the checkpoint) are the two hard exit criteria of
  every gate — state both when you close the gate.
- Adapt depth to the size of the demand: for a small demand, say which gates you
  are collapsing and why — but still checkpoint before mutating code or deploying.

Begin at the first applicable gate now. State which gate you are in.
