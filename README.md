# Conductor

A global CLI that turns any project into a **Claude-Code-conducted** project.
`conductor cdt init` analyzes your project and scaffolds Claude-Code-native
config into it — a relevant subset of 36 industry **role Agents + Skills** under
`.claude/`, the detected **stack**, and a generated **CLAUDE.md** describing the
roles and an 11-gate development flow (discovery → spec → security → architecture
→ test → code → quality gate → validation → delivery → observability → learning).

Conductor is **not a Claude Code plugin**. It is the tool that *prepares* a
project; the reasoning then happens in your Claude, driven by the project-local
`.claude/` and `CLAUDE.md`. Two memories ground every gate:

| Memory | Knows | Backed by |
|--------|-------|-----------|
| **Library (RAG)** | what good practice says — static books | `conductor library` → bge-m3 + ChromaDB |
| **Diary (Honcho)** | what *this* project decided & learned | `conductor journal` → Honcho + local mirror |

## Install

```bash
pipx install conductor          # or: pip install conductor
# from source:  pipx install --editable .
```

Gives you the `conductor` command (and the `cdt` alias).

## Use

```bash
# In a project directory:
conductor cdt init              # detect type/stack, generate .claude/ + CLAUDE.md
conductor cdt init --all        # scaffold all 36 roles (default: a relevant subset)
conductor cdt init --roles backend-engineer,security-engineer,...   # explicit set

# Grounding + memory (from the project root):
conductor library "bounded context boundaries"
conductor journal add --gate 4 --kind decision "chose hexagonal arch; ADR-1"
conductor journal recall "why this architecture?"

# Backends (Docker): RAG (Ollama + ChromaDB), GPU auto-detected
conductor up                    # start    | conductor down  | conductor ingest
```

Then open the project in Claude Code — the project-scoped `.claude/agents` and
`.claude/skills` load automatically (no plugin), and `CLAUDE.md` is picked up as
project context. Each role runs on a model sized to its cognitive load (`model:`
per agent — opus for architecture/security/strategy, sonnet for implementation,
haiku for light facilitation).

## What `conductor cdt init` generates

```
<project>/
  CLAUDE.md                     # roles + the 11-gate flow + the conductor CLI
  .claude/
    agents/<role>.md            # subset by type (Claude Code auto-loads these)
    skills/<skill>/SKILL.md     # the matching skills
  .cdt/
    config.json                 # enrollment (slug, type, Honcho workspace)
    stack/<TYPE>.md             # detected technologies (steers RAG queries)
    journal/                    # local diary mirror
```

## Layout

- `conductor/` — the Python package (CLI). `cli.py` (dispatch), `detect.py`
  (type/stack), `roles.py` (36-role registry), `scaffold.py` (generator),
  `library.py`/`journal.py`/`honcho_client.py`, and `rag/` (embed/ingest/stack).
- `conductor/templates/` — the 36 role Agents + Skills + `CLAUDE.md.tmpl` +
  `flow.md` (the 11-gate flow), copied into projects.
- `infra/conductor/` — the Docker RAG stack (Ollama + bge-m3 + ChromaDB).
- `infra/honcho/` — the self-hosted Honcho diary backend.
- `tools/validate.py` — the golden-rule validator over the templates (CI gate).

## Invariants

`python tools/validate.py` enforces 8 golden rules (R1–R8) over the templates:
role parity (36+36), frontmatter/YAML safety, semver, agent anchoring, skill
structure, the roles↔templates registry + 11-gate flow, and valid model tiers.
Runs in CI. See [tools/](tools/README.md).
