#!/usr/bin/env python3
"""`conductor cdt init|sync` — generate and keep alive a project's Claude-Code config.

`init` scaffolds, into the target project:
  .claude/agents/<role>.md          a relevant subset of role Agents
  .claude/skills/<skill>/SKILL.md   the matching Skills
  .cdt/config.json                  enrollment (slug, type, roles, Honcho workspace)
  .cdt/stack/<TYPE>.md              detected technologies (RAG-steering)
  .cdt/journal/                     local diary mirror
  CLAUDE.md                         project guide (roles + memory + 11-gate flow)

`sync` keeps CLAUDE.md **live**: it re-detects the stack, refreshes the roles,
and pulls the latest diary memory — regenerating only the managed region
(between markers) and preserving anything the human wrote below it.
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from . import roles as roles_mod
from .detect import VALID_TYPES, detect
from .project import (cdt_dir, config_path, find_project_root, force_utf8,
                      journal_dir, read_config, register_project, slugify,
                      stack_dir, write_config)

TEMPLATES = Path(__file__).resolve().parent / "templates"
DEFAULT_HONCHO_URL = "http://localhost:8000"

MANAGED_START = "<!-- conductor:managed:start"
MANAGED_END = "<!-- conductor:managed:end -->"
MEMORY_KINDS = ("decision", "solution", "error", "plan")
MEMORY_LIMIT = 15


# --- rendering ---------------------------------------------------------------

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


def _project_memory(root: Path, limit: int = MEMORY_LIMIT) -> str:
    """Recent durable diary entries (decisions/solutions/errors/plans), newest first."""
    entries = []
    for jf in sorted(journal_dir(root).glob("*.jsonl")):
        for line in jf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("kind") in MEMORY_KINDS:
                entries.append(e)
    if not entries:
        return "_No diary entries yet._"
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    lines = []
    for e in entries[:limit]:
        gate = f"gate {e['gate']}" if e.get("gate") is not None else "—"
        lines.append(f"- **[{gate}] {e.get('kind','')}** — {e.get('text','')}  "
                     f"_({e.get('ts','')})_")
    return "\n".join(lines)


def _render(root: Path, slug: str, ptype: str, selected: List[str]) -> str:
    tmpl = (TEMPLATES / "CLAUDE.md.tmpl").read_text(encoding="utf-8")
    flow = (TEMPLATES / "flow.md").read_text(encoding="utf-8")
    return (tmpl
            .replace("{project}", slug)
            .replace("{type}", ptype)
            .replace("{roles_table}", _roles_table(selected))
            .replace("{project_memory}", _project_memory(root))
            .replace("{flow}", flow))


def _managed_slice(text: str):
    """Returns (start, end) indices spanning the managed region (incl markers), or None."""
    s = text.find(MANAGED_START)
    e = text.find(MANAGED_END)
    if s == -1 or e == -1:
        return None
    return s, e + len(MANAGED_END)


def _write_claude_md(root: Path, slug: str, ptype: str, selected: List[str]) -> str:
    """Writes (init) or splices (sync) CLAUDE.md. Returns 'created' or 'synced'."""
    fresh = _render(root, slug, ptype, selected)
    out = root / "CLAUDE.md"
    if out.is_file():
        old = out.read_text(encoding="utf-8")
        old_span, new_span = _managed_slice(old), _managed_slice(fresh)
        if old_span and new_span:
            region = fresh[new_span[0]:new_span[1]]
            merged = old[:old_span[0]] + region + old[old_span[1]:]
            out.write_text(merged, encoding="utf-8")
            return "synced"
    out.write_text(fresh, encoding="utf-8")
    return "created"


# --- scaffolding -------------------------------------------------------------

def _copy_roles(project: Path, selected: List[str]) -> int:
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


def _resolve_selection(ptype: str, all_roles: bool, override: Optional[List[str]]):
    """Returns (selected, mode)."""
    if override:
        return roles_mod.select_roles(ptype, override=override), "custom"
    if all_roles:
        return roles_mod.select_roles(ptype, all_roles=True), "all"
    return roles_mod.select_roles(ptype), "subset"


def refresh_claude_md(root: Path) -> bool:
    """Best-effort live refresh of the managed region (called after journal writes)."""
    config = read_config(root)
    if config is None or not (root / "CLAUDE.md").is_file():
        return False
    selected = config.get("roles") or roles_mod.select_roles(config.get("type", "unknown"))
    try:
        _write_claude_md(root, config.get("project", root.name),
                         config.get("type", "unknown"), selected)
        return True
    except Exception:  # noqa: BLE001 — refresh is best-effort
        return False


# --- commands ----------------------------------------------------------------

def cmd_init(args) -> int:
    project = Path(args.path).resolve()
    if not project.is_dir():
        print(f"ERROR: not a directory: {project}", file=sys.stderr)
        return 2
    if config_path(project).is_file() and not args.force:
        print(f"Already enrolled: {config_path(project)} "
              "(use --force to re-init, or `conductor cdt sync` to refresh)")
        return 0

    det_type, techs, evidence = detect(project)
    ptype = args.type or det_type
    slug = slugify(args.name or project.name)
    override = [s.strip() for s in args.roles.split(",")] if args.roles else None
    try:
        selected, mode = _resolve_selection(ptype, args.all, override)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"[1/4] analyzing {project.name}: type={ptype}"
          + (f", detected={', '.join(techs)}" if techs else ""))
    n = _copy_roles(project, selected)
    print(f"[2/4] .claude/: {n} agents + {n} skills ({mode} for {ptype})")

    stack_dir(project).mkdir(parents=True, exist_ok=True)
    journal_dir(project).mkdir(parents=True, exist_ok=True)
    (stack_dir(project) / f"{ptype}.md").write_text(
        _stack_md(ptype, techs, evidence), encoding="utf-8")
    (cdt_dir(project) / ".gitignore").write_text("journal/\n", encoding="utf-8")
    write_config(project, {
        "project": slug, "type": ptype, "roles": selected, "roles_mode": mode,
        "honcho": {"workspace": slug, "base_url": args.honcho_url,
                   "session_prefix": "cdt"},
        "created": datetime.date.today().isoformat(),
    })
    register_project(project, slug, ptype)
    print(f"[3/4] .cdt/: enrolled '{slug}', stack -> {ptype}.md")
    state = _write_claude_md(project, slug, ptype, selected)
    print(f"[4/4] CLAUDE.md {state} ({len(selected)} roles + memory + 11-gate flow)")
    print("Done. `conductor cdt sync` keeps CLAUDE.md live as the project evolves.")
    return 0


def cmd_sync(args) -> int:
    root = Path(args.path).resolve() if args.path else find_project_root()
    config = read_config(root)
    if config is None:
        print(f"ERROR: not an enrolled project (no .cdt/ at {root}). "
              "Run `conductor cdt init` first.", file=sys.stderr)
        return 2

    slug = config.get("project", slugify(root.name))
    mode = config.get("roles_mode", "subset")
    det_type, techs, evidence = detect(root)
    ptype = args.type or (det_type if det_type != "unknown" else config.get("type", "unknown"))

    if mode == "all":
        selected = roles_mod.select_roles(ptype, all_roles=True)
    elif mode == "custom":
        selected = config.get("roles") or roles_mod.select_roles(ptype)
    else:
        selected = roles_mod.select_roles(ptype)  # subset re-computed for current type

    n = _copy_roles(root, selected)
    (stack_dir(root) / f"{ptype}.md").write_text(
        _stack_md(ptype, techs, evidence), encoding="utf-8")
    config.update({"type": ptype, "roles": selected, "roles_mode": mode})
    write_config(root, config)
    register_project(root, slug, ptype)
    state = _write_claude_md(root, slug, ptype, selected)

    print(f"synced '{slug}' (type={ptype}, {n} roles): stack refreshed, "
          f"diary memory pulled, CLAUDE.md {state}.")
    return 0


def main(argv: List[str]) -> int:
    force_utf8()
    # Dispatched as `conductor cdt init ...` / `conductor cdt sync ...`; the
    # action word is argv[0] when present, else default to init.
    action = "init"
    rest = argv
    if argv and argv[0] in ("init", "sync"):
        action, rest = argv[0], argv[1:]

    ap = argparse.ArgumentParser(prog=f"conductor cdt {action}")
    ap.add_argument("path", nargs="?", default=None if action == "sync" else ".",
                    help="project directory")
    ap.add_argument("--type", choices=VALID_TYPES, help="force the project type")
    if action == "init":
        ap.add_argument("--name", help="project name (default: directory name)")
        ap.add_argument("--all", action="store_true", help="scaffold all 36 roles")
        ap.add_argument("--roles", help="comma-separated role slugs (override the subset)")
        ap.add_argument("--honcho-url", default=DEFAULT_HONCHO_URL, help="Honcho base URL")
        ap.add_argument("--force", action="store_true", help="re-init (overwrite)")
    args = ap.parse_args(rest)

    return cmd_sync(args) if action == "sync" else cmd_init(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
