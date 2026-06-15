# Conductor

A technology-agnostic software-development **guidance plugin** for Claude Code.
It brings together 36 industry roles — each an **Agent** (a system prompt
anchored in reference books) with an actionable **Skill** — and conducts a
demand through an 11-gate flow so no critical step (discovery, spec, security,
architecture, test, code, quality gate, validation, delivery, observability,
learning) gets skipped.

## Install

### Locally (before publishing)

Fastest dev loop — load straight from the directory, no marketplace:

```bash
claude --plugin-dir /path/to/conductor
```

Or install through the bundled local marketplace (exercises the real flow). In
Claude Code:

```
/plugin marketplace add /path/to/conductor
/plugin install conductor@conductor
/reload-plugins
```

`conductor@conductor` is `<plugin-name>@<marketplace-name>` (both `conductor`).
Verify with `/plugin details conductor@conductor`, `/help` (see `/cdt`,
`/library`, `/journal`), and `/agents` (the 36 roles).

### From GitHub (after publishing)

```
/plugin marketplace add <user>/conductor
/plugin install conductor@conductor
```

### Optional Python extras

The `/library` (RAG) and `/journal` (diary) commands shell out to
`python -m rag.…` / `python -m cdt.…`. Install the package so those modules
resolve from any directory:

```bash
pip install -e .[rag]        # semantic search over the library (+ Ollama/bge-m3)
pip install -e .[honcho]     # the development diary (+ infra/honcho/ server)
```

The plugin's agents/skills/commands work without any of this; the extras only
power the two memories.

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
- `infra/honcho/` — self-hosted Honcho (docker-compose; reasoning provider is your choice).
- `tools/validate.py` — the golden-rule invariant validator (CI quality gate).

## Invariants

`python tools/validate.py` enforces 8 golden rules (R1–R8) that keep the plugin
consistent with `plano.md` — role parity, frontmatter/YAML safety, version sync,
agent/skill structure, flow integrity, and valid model tiers. It runs in CI as
the plugin's own Gate 7. See [tools/](tools/README.md).
