#!/usr/bin/env python3
"""`conductor cdt init [path]` — enroll a project: generate Claude-Code-native
config into it.

Creates in the target project:
  .claude/agents/<role>.md          a relevant subset of role Agents
  .claude/skills/<skill>/SKILL.md   the matching Skills
  .cdt/config.json                  enrollment (slug, type, Honcho workspace)
  .cdt/stack/<TYPE>.md              detected technologies (RAG-steering)
  .cdt/journal/                     local diary mirror
  CLAUDE.md                         project guide (roles + the 11-gate flow + CLI)

Claude Code auto-loads the project-scoped `.claude/` — no plugin needed.
"""
from __future__ import annotations

import argparse
import datetime
import shutil
import sys
from pathlib import Path
from typing import List

from . import roles as roles_mod
from .detect import VALID_TYPES, detect
from .project import (cdt_dir, config_path, force_utf8, journal_dir,
                      register_project, slugify, stack_dir, write_config)

TEMPLATES = Path(__file__).resolve().parent / "templates"
DEFAULT_HONCHO_URL = "http://localhost:8000"


def _stack_md(ptype: str, techs: List[str], evidence: List[str]) -> str:
    tech_lines = "\n".join(f"- {t}" for t in techs) or "- _(to be completed)_"
    ev = ", ".join(evidence) if evidence else "none"
    return f"""# Stack — {ptype}

Technologies this project uses. Agents read this so their `conductor library`
(RAG) queries are **project-aware**.

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


def _roles_table(selected: List[str]) -> str:
    rows = ["| Role | Area | Skill |", "|------|------|-------|"]
    for slug in selected:
        r = roles_mod.ROLES[slug]
        rows.append(f"| `{slug}` | {r.area} | `{r.skill}` |")
    return "\n".join(rows)


def _copy_roles(project: Path, selected: List[str]) -> int:
    """Copies the selected agent + matching skill templates into .claude/."""
    agents_dst = project / ".claude" / "agents"
    skills_dst = project / ".claude" / "skills"
    agents_dst.mkdir(parents=True, exist_ok=True)
    skills_dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for slug in selected:
        src_agent = TEMPLATES / "agents" / f"{slug}.md"
        if src_agent.is_file():
            shutil.copyfile(src_agent, agents_dst / f"{slug}.md")
        skill = roles_mod.ROLES[slug].skill
        src_skill = TEMPLATES / "skills" / skill / "SKILL.md"
        if src_skill.is_file():
            (skills_dst / skill).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_skill, skills_dst / skill / "SKILL.md")
        n += 1
    return n


def _write_claude_md(project: Path, *, slug: str, ptype: str,
                     selected: List[str]) -> Path:
    tmpl = (TEMPLATES / "CLAUDE.md.tmpl").read_text(encoding="utf-8")
    flow = (TEMPLATES / "flow.md").read_text(encoding="utf-8")
    content = (tmpl
               .replace("{project}", slug)
               .replace("{type}", ptype)
               .replace("{roles_table}", _roles_table(selected))
               .replace("{flow}", flow))
    out = project / "CLAUDE.md"
    out.write_text(content, encoding="utf-8")
    return out


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="conductor cdt init",
                                 description="Enroll a project in Conductor.")
    ap.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    ap.add_argument("--type", choices=VALID_TYPES, help="force the project type")
    ap.add_argument("--name", help="project name (default: directory name)")
    ap.add_argument("--all", action="store_true", help="scaffold all 36 roles")
    ap.add_argument("--roles", help="comma-separated role slugs (overrides the subset)")
    ap.add_argument("--honcho-url", default=DEFAULT_HONCHO_URL, help="Honcho base URL")
    ap.add_argument("--force", action="store_true", help="re-enroll (overwrite)")
    args = ap.parse_args(argv)
    force_utf8()

    project = Path(args.path).resolve()
    if not project.is_dir():
        print(f"ERROR: not a directory: {project}", file=sys.stderr)
        return 2
    if config_path(project).is_file() and not args.force:
        print(f"Already enrolled: {config_path(project)} (use --force to overwrite)")
        return 0

    det_type, techs, evidence = detect(project)
    ptype = args.type or det_type
    slug = slugify(args.name or project.name)
    override = [s.strip() for s in args.roles.split(",")] if args.roles else None
    try:
        selected = roles_mod.select_roles(ptype, all_roles=args.all, override=override)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"[1/4] analyzing {project.name}: type={ptype}"
          + (f", detected={', '.join(techs)}" if techs else ""))

    n = _copy_roles(project, selected)
    print(f"[2/4] .claude/: {n} agents + {n} skills "
          f"({'all 36' if args.all else 'subset for ' + ptype})")

    stack_dir(project).mkdir(parents=True, exist_ok=True)
    journal_dir(project).mkdir(parents=True, exist_ok=True)
    stack_file = stack_dir(project) / f"{ptype}.md"
    if not stack_file.is_file() or args.force:
        stack_file.write_text(_stack_md(ptype, techs, evidence), encoding="utf-8")
    (cdt_dir(project) / ".gitignore").write_text("journal/\n", encoding="utf-8")
    write_config(project, {
        "project": slug,
        "type": ptype,
        "honcho": {"workspace": slug, "base_url": args.honcho_url,
                   "session_prefix": "cdt"},
        "created": datetime.date.today().isoformat(),
    })
    register_project(project, slug, ptype)
    print(f"[3/4] .cdt/: enrolled '{slug}', stack -> {stack_file.name}")

    claude_md = _write_claude_md(project, slug=slug, ptype=ptype, selected=selected)
    print(f"[4/4] {claude_md.name} generated ({len(selected)} roles + 11-gate flow)")
    print("Done. Open the project in Claude Code; run `conductor up` for RAG.")
    if ptype == "unknown" or not techs:
        print("Note: type/stack incomplete — finalize .cdt/stack and re-run with --type.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
