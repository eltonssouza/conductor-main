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

import difflib
import sys
from pathlib import Path
from typing import List, Optional

# Valid top-level commands, used for unknown-command suggestions.
COMMANDS = (
    "init", "sync", "detect", "list", "library", "journal", "up", "down",
    "ingest", "honcho", "honcho-setup", "update", "quickstart",
    "mcp", "odysseus", "doc", "cdt", "version", "help",
)


def _version() -> str:
    """The Conductor version.

    Prefer the source `pyproject.toml` when it sits next to the package — for an
    editable/source install that is the *live* version, which `git pull` /
    `cdt update` change without a reinstall (installed metadata would be stale).
    Fall back to installed package metadata for a wheel/pipx install with no
    source tree alongside.
    """
    try:
        import re
        pp = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pp.is_file():
            m = re.search(r'^version = "([^"]+)"', pp.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1)
    except OSError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("conductor")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return "unknown"

USAGE = """cdt <command> [args]   (alias: conductor)

Commands:
  cdt init [path]            Enroll a project: generate .claude/ (agents+skills),
                             .cdt/ (stack, diary), and a project CLAUDE.md.
  cdt sync [path]            Refresh CLAUDE.md (live): re-detect stack, roles, and
                             pull the latest diary memory into the managed region.
  init | sync [path]         Aliases for `cdt init` / `cdt sync`.
  detect [path]              Show the detected type/tech and the library stacks
                             `cdt up` would auto-ingest for this project.
  list                       List the projects enrolled with Conductor.
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
  version | --version        Print the installed Conductor version.
  mcp                        Run Conductor's memories (library + journal) as an MCP stdio server.
  doc <file.md> [--format docx|pdf|both] [--out FILE] [--title T]
                             Render a Markdown spec/questions file to a .docx
                             and/or .pdf deliverable (needs the [docs] extra).
  odysseus install --projects <dir...> [--home <path>] [--mount /workspace] [--with-mcp <src>]
                             Install ALL Conductor skills into an Odysseus Brain
                             (global, once) + give its agent access to host folder(s).
  odysseus doctor [--home <path>]
                             Check an existing Conductor↔Odysseus install.

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
    if argv[0] in ("-V", "--version", "version"):
        print(f"conductor {_version()}")
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

    if cmd == "list":
        from .project import force_utf8, list_projects
        force_utf8()
        projects = list_projects()
        if not projects:
            print("No projects enrolled yet. Run `cdt init` in a project.")
            return 0
        width = max(len(p["slug"]) for p in projects)
        print(f"{len(projects)} enrolled project(s):")
        for p in projects:
            print(f"  {p['slug']:<{width}}  {p.get('type', '?'):<9}  {p['path']}")
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

    if cmd == "mcp":
        from .mcp_server import main as mcp_main
        return mcp_main(rest)

    if cmd == "odysseus":
        from .install_odysseus import main as odysseus_main
        return odysseus_main(rest)

    if cmd == "doc":
        from .docgen import main as doc_main
        return doc_main(rest)

    print(f"cdt: unknown command: {cmd}", file=sys.stderr)
    suggestions = difflib.get_close_matches(cmd, COMMANDS, n=1)
    if suggestions:
        print(f"did you mean '{suggestions[0]}'?", file=sys.stderr)
    print("run `cdt --help` for the list of commands.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
