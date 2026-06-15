# Conductor

A technology-agnostic software-development **guidance plugin** for Claude Code.
It brings together 36 industry roles — each an **Agent** (a system prompt
anchored in reference books) with an actionable **Skill** — and conducts a
demand through an 11-gate flow so no critical step (discovery, spec, security,
architecture, test, code, quality gate, validation, delivery, observability,
learning) gets skipped.

## The flow — `/cdt`

```
/cdt "add a WhatsApp button to the Angular app"
```

Runs the demand through the **11 gates in order**, delegating to the right roles
at each step and refusing to advance until each gate's exit criterion is met.
Each role runs on a model sized to its cognitive load (`model:` per agent —
opus for architecture/security/strategy, sonnet for implementation, haiku for
light facilitation).

## Two memories that ground every gate

| Memory | What it knows | How |
|--------|---------------|-----|
| **Library (RAG)** | what good practice says — static books | `/library "<question>"` → bge-m3 + ChromaDB. See [rag/](rag/README.md). |
| **Diary (Honcho)** | what *this* project decided & learned — dynamic | `/journal add/recall` → Honcho + local mirror. See [cdt/](cdt/README.md). |

## Per-project usage — `/cdt init`

Conductor is opt-in per project. Enroll one with:

```
/cdt init
```

This scaffolds `.cdt/` (project type, tech stack, diary), so the RAG becomes
**project-aware** and the diary records the project's history. Enrolled projects
are tracked in `~/.claude/conductor/projects.json`.

## Layout

- `agents/` — 36 role Agents (system prompt + reference books + model tier).
- `skills/` — 36 matching Skills (`When to use` + numbered steps).
- `commands/` — `/cdt` (flow + `init`), `/library` (RAG), `/journal` (diary).
- `rag/` — semantic search over the library (optional extra `[rag]`).
- `cdt/` — per-project enrollment + development diary (optional extra `[honcho]`).
- `infra/honcho/` — self-hosted Honcho (docker-compose, DeepSeek reasoning).
- `tools/validate.py` — the golden-rule invariant validator (CI quality gate).

## Invariants

`python tools/validate.py` enforces 8 golden rules (R1–R8) that keep the plugin
consistent with `plano.md` — role parity, frontmatter/YAML safety, version sync,
agent/skill structure, flow integrity, and valid model tiers. It runs in CI as
the plugin's own Gate 7. See [tools/](tools/README.md).
