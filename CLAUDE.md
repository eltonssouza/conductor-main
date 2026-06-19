# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Responda SEMPRE em pt-BR (português do Brasil), independentemente do idioma da pergunta.

## Project Identity

- **Type:** global **CLI** (`cdt`, alias `conductor`), distributed via pipx/pip.
  NOT a Claude Code plugin (that model was dropped).
- **What it does:** `cdt init` analyzes a project and scaffolds
  Claude-Code-native config into it — a relevant subset of 36 role Agents +
  Skills under `.claude/`, the detected stack under `.cdt/`, and a generated
  `CLAUDE.md` (roles + the 11-gate flow + how to use the CLI). The reasoning
  happens in the user's Claude, not inside Conductor.
- **Two memories:** `cdt library` (RAG over reference books — bge-m3 +
  ChromaDB) and `cdt journal` (per-project diary — Honcho + local JSONL
  mirror). Backends run in Docker (`infra/`); `cdt up` starts them.
- **Core is pure stdlib;** `chromadb`/`honcho-ai` are optional extras
  (`[rag]`, `[honcho]`).

## Layout

- `conductor/` — the package: `cli.py` (dispatch), `detect.py`, `roles.py`
  (36-role registry: role→skill/area/types), `scaffold.py` (the generator),
  `library.py`, `journal.py`, `honcho_client.py`, `honcho_setup.py`, and
  `rag/` (core/ingest/bootstrap/stack).
- `conductor/templates/` — `agents/` (36), `skills/` (36), `CLAUDE.md.tmpl`,
  `flow.md` (the 11-gate flow). Copied into target projects.
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
