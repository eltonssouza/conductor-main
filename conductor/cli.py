#!/usr/bin/env python3
"""`conductor` — the global CLI entry point.

Subcommands:
  conductor cdt init [path]              scaffold .claude/ + .cdt/ + CLAUDE.md
  conductor library "<question>"         RAG search over the reference books
  conductor journal add|recall|log ...   per-project development diary
  conductor up | down                    start/stop the Docker RAG stack (GPU auto)
  conductor ingest                       (re)build the index

`cdt` is an alias for `conductor` (e.g. `cdt init`).
"""
from __future__ import annotations

import sys
from typing import List, Optional

USAGE = """conductor <command> [args]

Commands:
  cdt init [path]            Enroll a project: generate .claude/ (agents+skills),
                             .cdt/ (stack, diary), and a project CLAUDE.md.
  init [path]                Alias for `cdt init`.
  library "<question>"       Semantic search over the reference books (RAG).
  journal add|recall|log     Per-project development diary.
  up | down                  Start / stop the Docker RAG stack (auto-detects GPU).
  ingest                     (Re)build the index in the running stack.
  honcho-setup               Choose the Honcho diary reasoning provider.

Run `conductor <command> --help` for command options.
"""


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    cmd, rest = argv[0], argv[1:]

    # `cdt init ...` (and bare `init ...`)
    if cmd == "cdt":
        if rest and rest[0] == "init":
            from .scaffold import main as scaffold_main
            return scaffold_main(rest[1:])
        print("usage: conductor cdt init [path]", file=sys.stderr)
        return 2
    if cmd == "init":
        from .scaffold import main as scaffold_main
        return scaffold_main(rest)

    if cmd == "library":
        from .library import main as library_main
        return library_main(rest)

    if cmd == "journal":
        from .journal import main as journal_main
        return journal_main(rest)

    if cmd in ("up", "down"):
        from .rag.stack import main as stack_main
        return stack_main([cmd, *rest])

    if cmd == "ingest":
        from .rag.bootstrap import main as bootstrap_main
        return bootstrap_main()

    if cmd == "honcho-setup":
        from .honcho_setup import main as honcho_setup_main
        return honcho_setup_main(rest)

    print(f"unknown command: {cmd}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
