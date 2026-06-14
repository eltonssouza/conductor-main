# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Responda SEMPRE em pt-BR (português do Brasil), independentemente do idioma da pergunta.

## Project status

Greenfield. Repository is currently empty — no source, build files, or docs exist yet. Update this file as the codebase takes shape.

## Project Identity

- **Type:** Claude Code plugin (`conductor`).
- **Architecture:** 3 pillars; pure-stdlib Python core (no third-party runtime deps).
- **CLI:** dual-mode import — usable both as a CLI entry point and as an imported library.
- **Versioning:** always bump the patch digit; on rollover `99` → next minor; keep `plugin.json` and `pyproject.toml` in sync (bump both together).

## Notes

When real code lands, replace the sections above with concrete build/lint/test commands and the actual module layout. Do not document architecture that does not yet exist in the tree.
