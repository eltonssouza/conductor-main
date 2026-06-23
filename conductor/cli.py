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
from pathlib import Path
from typing import List, Optional

USAGE = """cdt <command> [args]   (alias: conductor)

Commands:
  cdt init [path]            Enroll a project: generate .claude/ (agents+skills),
                             .cdt/ (stack, diary), and a project CLAUDE.md.
  cdt sync [path]            Refresh CLAUDE.md (live): re-detect stack, roles, and
                             pull the latest diary memory into the managed region.
  init | sync [path]         Aliases for `cdt init` / `cdt sync`.
  detect [path]              Show the detected type/tech and the library stacks
                             `cdt up` would auto-ingest for this project.
  library "<question>"       Semantic search over the reference books (RAG).
  library status             Show what is ingested (books, categories, chunk counts).
  library stacks             Choose which language/framework stacks to ingest (interactive).
  library reindex            Index any library files not yet in ChromaDB (incremental).
  library add <file.md>      Index specific .md file(s) already under the library.
  journal add|recall|log     Per-project development diary.
  up | down                  Start / stop the Docker RAG stack (auto-detects GPU).
  ingest                     (Re)build the index in the running stack.
  honcho setup               Choose the Honcho diary reasoning provider.
  honcho up | down           Start / stop the Honcho diary backend (Docker).
  update [--reinstall]       Pull the latest source (editable/source install).
  quickstart                 Print the ordered path: install -> first /cdt feature.

Run `cdt <command> --help` for command options.
"""

QUICKSTART = """Conductor quickstart - from install to your first feature

1. Install (once) - one line
   macOS/Linux:  curl -fsSL https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.sh | sh
   Windows:      irm https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.ps1 | iex

2. Start the two memories in Docker (once per machine)
   cdt up                                 # RAG: Ollama + ChromaDB + ingest the language-agnostic core
   cdt library status                     # verify what got ingested
   cdt honcho setup                       # diary reasoning - pick a provider (deepseek/openai/ollama/...); ollama is key-free
   cdt honcho up                          # the Honcho diary backend

3. Enroll a project - and add its stack to the library
   cd /path/to/your-project
   cdt init                               # scaffold .claude/ + .cdt/ + CLAUDE.md + /cdt + hooks
   cdt detect                             # see the project's languages/frameworks
   cdt up                                 # re-run FROM the project: ingests its stack books too

4. Reload Claude Code in that project     # so the /cdt command and the hooks load

5. Drive your first feature through the gates (inside Claude Code)
   /cdt implement <your feature>          # interactive: stops for your approval at each gate

Handy along the way:
   cdt library "<question>"               # ground an answer in the reference books
   cdt journal recall "<question>"        # recall what this project already decided
   cdt journal log --kind error,solution  # list problems already solved
   cdt sync                               # after upgrading Conductor: refresh an enrolled project
"""


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd == "quickstart":
        print(QUICKSTART)
        return 0

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

    if cmd == "detect":
        from .detect import detect, library_stacks
        from .project import find_project_root, force_utf8
        force_utf8()
        root = Path(rest[0]).resolve() if rest else find_project_root()
        ptype, techs, _ = detect(root)
        stacks = library_stacks(root)
        print(f"project: {root}")
        print(f"type:    {ptype}")
        print(f"tech:    {', '.join(techs) or 'none detected'}")
        print(f"stacks:  {', '.join(stacks) or 'none (core, language-agnostic only)'}")
        if stacks:
            print(f"\n`cdt up` from here auto-ingests core + these stacks.\n"
                  f"Force a set with:  CONDUCTOR_LIBRARY_STACKS={','.join(stacks)} cdt up")
        return 0

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
