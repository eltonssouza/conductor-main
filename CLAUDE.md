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
  `honcho_setup.py`, and `rag/` (core/ingest/bootstrap/stack).
- `conductor/templates/` — `agents/` (36), `skills/` (36), `commands/`
  (`cdt.md` Claude driver, `cdt.opencode.md` OpenCode driver), `CLAUDE.md.tmpl`
  + `AGENTS.md.tmpl` (guide variants), `flow.md` (the 11-gate flow). Copied/
  translated into target projects per target.
- `infra/conductor/` (RAG stack) and `infra/honcho/` (diary backend) — Docker.
- `tools/validate.py` — invariant validator over the templates (CI gate, R1–R8).

## Conventions

- **Versioning:** always bump the patch digit in `pyproject.toml`; on rollover
  `99` → next minor. (There is no longer a `plugin.json` to keep in sync.)
- **Language:** all project artifacts in English EXCEPT `plano.md` (stays pt-BR,
  historical) and chat responses (pt-BR, per Idioma above).
- **Validation:** `python tools/validate.py` must exit 0 (R1–R8 over templates).
- **Role↔skill pairing** is 1:1 and lives in `conductor/roles.py`; keep agent
  templates, skill templates, and that registry in sync (R7 enforces it).
