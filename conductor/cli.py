#!/usr/bin/env python3
"""`cdt` — the global CLI entry point (`conductor` is a kept alias).

Subcommands:
  cdt init [path]                  scaffold .claude/ + .cdt/ + CLAUDE.md
  cdt library "<question>"         RAG search over the reference books
  cdt journal add|recall|log ...   per-project development diary
  cdt up | down                    start/stop the Docker RAG stack (GPU auto)
  cdt ingest                       (re)build the index

Both `cdt` and `conductor` invoke this; `cdt` is canonical in the docs.
"""
from __future__ import annotations

import sys
from typing import List, Optional

USAGE = """cdt <command> [args]   (alias: conductor)

Commands:
  cdt init [path]            Enroll a project: generate .claude/ (agents+skills),
                             .cdt/ (stack, diary), and a project CLAUDE.md.
  cdt sync [path]            Refresh CLAUDE.md (live): re-detect stack, roles, and
                             pull the latest diary memory into the managed region.
  init | sync [path]         Aliases for `cdt init` / `cdt sync`.
  library "<question>"       Semantic search over the reference books (RAG).
  library reindex            Index any library files not yet in ChromaDB (incremental).
  library add <file.md>      Index specific .md file(s) already under the library.
  journal add|recall|log     Per-project development diary.
  up | down                  Start / stop the Docker RAG stack (auto-detects GPU).
  ingest                     (Re)build the index in the running stack.
  viewer                     3D map of the library embeddings (filter by profile).
  honcho setup               Choose the Honcho diary reasoning provider.
  honcho up | down           Start / stop the Honcho diary backend (Docker).
  update [--reinstall]       Pull the latest source (editable/source install).

Run `cdt <command> --help` for command options.
"""


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    cmd, rest = argv[0], argv[1:]

    # `cdt init|sync ...` (and bare `init`/`sync`)
    if cmd == "cdt":
        if rest and rest[0] in ("init", "sync"):
            from .scaffold import main as scaffold_main
            return scaffold_main(rest)
        print("usage: cdt init|sync [path]", file=sys.stderr)
        return 2
    if cmd in ("init", "sync"):
        from .scaffold import main as scaffold_main
        return scaffold_main([cmd, *rest])

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

    if cmd == "viewer":
        from .viewer import main as viewer_main
        return viewer_main(rest)

    if cmd == "honcho-setup":
        from .honcho_setup import main as honcho_setup_main
        return honcho_setup_main(rest)

    if cmd == "honcho":
        if rest and rest[0] == "setup":
            from .honcho_setup import main as honcho_setup_main
            return honcho_setup_main(rest[1:])
        if rest and rest[0] in ("up", "down"):
            from .honcho_stack import main as honcho_stack_main
            return honcho_stack_main(rest)
        print("usage: cdt honcho setup|up|down", file=sys.stderr)
        return 2

    if cmd == "update":
        from .update import main as update_main
        return update_main(rest)

    print(f"unknown command: {cmd}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
