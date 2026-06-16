"""Conductor — a global CLI that turns any project into a Claude-Code-conducted
project.

`conductor cdt init` analyzes a project and scaffolds Claude-Code-native config
into it: a relevant subset of role Agents + Skills under `.claude/`, a detected
stack, and a generated `CLAUDE.md`. `conductor library` grounds answers in the
reference books (RAG), and `conductor journal` keeps a per-project development
diary. The RAG and diary backends run in Docker (see infra/).

Not a Claude Code plugin: the reasoning happens in the user's Claude, driven by
the project-local `.claude/` and `CLAUDE.md` this tool generates.
"""

__version__ = "0.2.9"
