"""Conductor per-project layer.

`cdt init` enrolls a project (creates `.cdt/`, detects the stack); the
development diary (`/journal`) records each cycle's reasoning/decisions/errors/
solutions into a long-term memory (Honcho) with a local JSONL mirror.

Pure stdlib except the optional `honcho` SDK (extra `[honcho]`); the diary
degrades to the local mirror when Honcho is absent.
"""
