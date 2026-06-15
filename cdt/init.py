#!/usr/bin/env python3
"""`python -m cdt.init` — enroll a project in Conductor.

Scaffolds `.cdt/` at the project root, best-effort detects the project type and
technologies from its manifests, writes `.cdt/stack/<TYPE>.md` and
`.cdt/config.json`, and registers the project in the global registry. The
`/cdt init` command then lets Claude read the real manifests and finalize the
stack file with the exact technologies.

  python -m cdt.init                 # enroll the current directory
  python -m cdt.init path/to/project # enroll another directory
  python -m cdt.init --type backend  # force the type
  python -m cdt.init --force         # re-enroll (overwrite config/stack)
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import List, Tuple

from .project import (cdt_dir, config_path, force_utf8, journal_dir,
                      register_project, slugify, stack_dir, write_config)

VALID_TYPES = ("backend", "frontend", "mobile", "fullstack", "library",
               "data", "unknown")
DEFAULT_HONCHO_URL = "http://localhost:8000"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def detect(root: Path) -> Tuple[str, List[str], List[str]]:
    """Best-effort (type, technologies, evidence) from root manifests.

    Conservative: when signals are mixed it prefers `fullstack`; when nothing is
    recognized it returns `unknown` so the command/owner can classify.
    """
    techs: List[str] = []
    evidence: List[str] = []
    front = back = mobile = False

    def has(name: str) -> bool:
        return (root / name).exists()

    # --- JS/TS ecosystem (package.json) ---
    pkg = _read_json(root / "package.json") if has("package.json") else {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if pkg:
        evidence.append("package.json")
    if has("angular.json") or "@angular/core" in deps:
        front = True; techs.append("Angular")
    if "react" in deps:
        if "react-native" in deps:
            mobile = True; techs.append("React Native")
        else:
            front = True; techs.append("React")
    if "vue" in deps:
        front = True; techs.append("Vue")
    if "svelte" in deps:
        front = True; techs.append("Svelte")
    if "next" in deps:
        front = True; techs.append("Next.js")
    if any((root / f).exists() for f in ("vite.config.js", "vite.config.ts")):
        front = True; techs.append("Vite")
    if "express" in deps or "fastify" in deps or "@nestjs/core" in deps:
        back = True; techs.append("Node.js")

    # --- backend manifests ---
    for f, tech in (("pom.xml", "Java/Maven"), ("build.gradle", "Java/Gradle"),
                    ("go.mod", "Go"), ("Gemfile", "Ruby"),
                    ("composer.json", "PHP"), ("Cargo.toml", "Rust")):
        if has(f):
            back = True; techs.append(tech); evidence.append(f)
    if has("requirements.txt") or has("pyproject.toml"):
        back = True; techs.append("Python"); evidence.append("requirements/pyproject")
    if any(root.glob("*.csproj")):
        back = True; techs.append(".NET"); evidence.append("*.csproj")

    # --- mobile manifests ---
    if has("pubspec.yaml"):
        mobile = True; techs.append("Flutter"); evidence.append("pubspec.yaml")
    if has("android") and has("ios"):
        mobile = True; evidence.append("android/+ios/")
    if any(root.glob("*.xcodeproj")):
        mobile = True; techs.append("iOS/Xcode"); evidence.append("*.xcodeproj")

    if mobile:
        ptype = "mobile"
    elif front and back:
        ptype = "fullstack"
    elif front:
        ptype = "frontend"
    elif back:
        ptype = "backend"
    else:
        ptype = "unknown"

    # de-dupe preserving order
    techs = list(dict.fromkeys(techs))
    return ptype, techs, evidence


def _stack_md(ptype: str, techs: List[str], evidence: List[str]) -> str:
    tech_lines = "\n".join(f"- {t}" for t in techs) or "- _(to be completed)_"
    ev = ", ".join(evidence) if evidence else "none"
    return f"""# Stack — {ptype}

Technologies this project uses. Agents read this so their `/library` (RAG)
queries are **project-aware** (e.g. ground answers in the stack's frameworks).

## Detected
{tech_lines}

## To complete (owner / Conductor)
- Language(s) & versions:
- Framework(s):
- Datastore(s):
- Build / package manager:
- Testing tools:
- Notable libraries / constraints:

<!-- detection evidence: {ev} -->
"""


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Enroll a project in Conductor.")
    ap.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    ap.add_argument("--type", choices=VALID_TYPES, help="force the project type")
    ap.add_argument("--name", help="project name (default: directory name)")
    ap.add_argument("--honcho-url", default=DEFAULT_HONCHO_URL, help="Honcho base URL")
    ap.add_argument("--force", action="store_true", help="re-enroll (overwrite)")
    args = ap.parse_args(argv)
    force_utf8()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    if config_path(root).is_file() and not args.force:
        print(f"Already enrolled: {config_path(root)} (use --force to overwrite)")
        return 0

    det_type, techs, evidence = detect(root)
    ptype = args.type or det_type
    slug = slugify(args.name or root.name)

    # scaffold
    stack_dir(root).mkdir(parents=True, exist_ok=True)
    journal_dir(root).mkdir(parents=True, exist_ok=True)
    stack_file = stack_dir(root) / f"{ptype}.md"
    if not stack_file.is_file() or args.force:
        stack_file.write_text(_stack_md(ptype, techs, evidence), encoding="utf-8")
    # local journal mirror is project-private by default
    (cdt_dir(root) / ".gitignore").write_text("journal/\n", encoding="utf-8")

    config = {
        "project": slug,
        "type": ptype,
        "honcho": {
            "workspace": slug,
            "base_url": args.honcho_url,
            "session_prefix": "cdt",
        },
        "created": datetime.date.today().isoformat(),
    }
    write_config(root, config)
    register_project(root, slug, ptype)

    print(f"Enrolled '{slug}' ({ptype}) at {root}")
    print(f"  config: {config_path(root)}")
    print(f"  stack:  {stack_file}")
    if techs:
        print(f"  detected: {', '.join(techs)}")
    if ptype == "unknown" or not techs:
        print("  note: type/stack incomplete — let `/cdt init` finalize it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
