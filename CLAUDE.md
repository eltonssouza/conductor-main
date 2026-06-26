# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Responda SEMPRE em pt-BR (português do Brasil), independentemente do idioma da pergunta.

## Project Identity

- **Type:** global **CLI** (`cdt`, alias `conductor`), distributed via pipx/pip.
  NOT a Claude Code plugin (that model was dropped).
- **What it does:** `cdt init` analyzes a project and scaffolds harness-native
  config into it — a relevant subset of 36 role Agents + Skills, the detected
  stack under `.cdt/`, and a generated project guide (roles + the 11-gate flow +
  how to use the CLI). The reasoning happens in the user's harness, not inside
  Conductor.
- **Loop engineering:** beyond the interactive `/cdt` driver, init scaffolds an
  autonomous `/cdt-triage` automation (discovery→maker-in-worktree→checker, state
  in the journal) and MCP connector config. Conductor's own memories run as an MCP
  server (`cdt mcp` → tools `library_search`/`journal_recall`/`journal_add`,
  optional `[mcp]` extra); third-party connector stubs (GitHub/Slack) ship
  disabled. The six per-target emitters are `emit_roles/driver/hooks/automations/
  mcp/guide`.
- **Multi-harness (`--target`):** the same neutral material is projected per AI
  harness by an adapter in `conductor/targets/`. Four targets: `claude` →
  `.claude/` + `CLAUDE.md`; `opencode` → `.opencode/` (agents+skills+command+
  plugin) + `AGENTS.md` + `opencode.json`; `codex` → `.agents/skills/` (roles
  folded into skills) + `AGENTS.md`; `pi` → `.pi/` (skills+prompt+extension) +
  `AGENTS.md`. `cdt init --target claude|opencode|codex|pi|all` (default:
  auto-detect, else claude); chosen targets persist in `.cdt/config.json` so
  `sync` re-emits them. Codex/Pi have no auto-subagents → a role's persona is
  folded into its skill (`base.merge_role_skill`); only Claude & Pi capture
  prompts for live memory (Pi via its `input` event → `cdt journal observe --text`).
- **Odysseus (global, not per-project):** Odysseus (self-hosted AI workspace in
  Docker) integrates via the dedicated `cdt odysseus install --projects <dir>`
  command (`conductor/install_odysseus.py`), NOT `cdt init`. It installs ALL
  skills once into the Odysseus "Brain" (`data/skills/conductor/`, frontmatter
  `status: published` + `owner` + `category: conductor` so `index_for` surfaces
  them), and wires the agent's host-folder access via a `docker-compose.override.yml`
  bind-mount + a `data/settings.json` `tool_path_extra_roots` patch. It reuses
  `OdysseusTarget` (in `targets/odysseus.py`) but that target is deliberately NOT
  in the `targets/__init__.py` registry, so init/sync never touch Odysseus. MCP
  (`cdt mcp` tools) is phase 2 — needs Conductor inside the container + backends.
- **Two memories:** `cdt library` (RAG over reference books — bge-m3 +
  ChromaDB) and `cdt journal` (per-project diary — Honcho + local JSONL
  mirror). Backends run in Docker (`infra/`); `cdt up` starts them.
- **Core is pure stdlib;** `chromadb`/`honcho-ai` are optional extras
  (`[rag]`, `[honcho]`).

## Layout

- `conductor/` — the package: `cli.py` (dispatch), `detect.py`, `roles.py`
  (36-role registry: role→skill/area/types), `scaffold.py` (the generator —
  harness-neutral steps only), `targets/` (per-harness adapters: `base.py`
  Target protocol + shared guide render, `claude.py`, `opencode.py`, registry
  in `__init__.py`), `library.py`, `journal.py`, `honcho_client.py`,
  `honcho_setup.py`, `mcp_server.py` (the `cdt mcp` stdio server),
  `install_odysseus.py` (the `cdt odysseus install` global Brain command),
  `docgen.py` (the `cdt doc` Markdown→.docx/.pdf renderer, optional `[docs]`
  extra: python-docx + reportlab),
  and `rag/` (core/ingest/bootstrap/stack).
- `conductor/templates/` — `agents/` (36), `skills/` (36), `commands/`
  (`cdt.md` Claude driver, `cdt.opencode.md`/`cdt.codex.md`/`cdt.pi.md` variants,
  and `intake.md` — the `/cdt-intake` triage+spec front door: classify the demand,
  optionally emit a pt-BR client-questions doc, write a rich spec (screens→behavior,
  backend rules→validations) grounded in the library, then hand off to `/cdt`),
  `automations/` (`triage.md`, the `/cdt-triage` autonomous loop), `CLAUDE.md.tmpl`
  + `AGENTS.md.tmpl` (guide variants), `flow.md` (the 11-gate flow). Copied/
  translated into target projects per target.
- `infra/conductor/` (RAG stack), `infra/honcho/` (diary backend), and
  `infra/mcp/` (the standalone Conductor MCP server: `cdt mcp --transport
  streamable-http` in Docker, exposes library+journal at `:8808/mcp` for a
  networked harness like Odysseus) — Docker.
- `tools/validate.py` — invariant validator over the templates (CI gate, R1–R14;
  R14 = the `/cdt-intake` command has triage + the spec skeleton + library grounding).

## Conventions

- **Versioning:** always bump the patch digit in `pyproject.toml`; on rollover
  `99` → next minor. (There is no longer a `plugin.json` to keep in sync.)
- **Language:** all project artifacts in English; chat responses in pt-BR (per
  Idioma above).
- **Validation:** `python tools/validate.py` must exit 0 (R1–R14 over templates;
  R12 = the triage automation template, R13 = MCP catalog + `emit_mcp` wiring,
  R14 = the `/cdt-intake` triage+spec command).
- **Role↔skill pairing** is 1:1 and lives in `conductor/roles.py`; keep agent
  templates, skill templates, and that registry in sync (R7 enforces it).
