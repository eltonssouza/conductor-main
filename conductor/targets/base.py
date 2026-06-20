"""Harness target abstraction — what differs between Claude Code, OpenCode, etc.

A **Target** knows how to project Conductor's harness-neutral material (the 36
role agents/skills, the `/cdt` flow driver, the live-memory hooks, and the
project guide) into one AI harness's native layout, file naming, frontmatter
dialect, and hook/plugin mechanism.

Everything *above* the target — stack detection, the `.cdt/` memory tree, the
config + registry — stays in `scaffold.py` and is shared by all targets. The
role/skill/flow **content** is also neutral; targets only re-shape its packaging.

The guide body (CLAUDE.md / AGENTS.md) is rendered here once from a template the
target chooses, so a target picks its filename and template variant rather than
re-implementing the splice that keeps the human's edits below the managed region.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple

from .. import roles as roles_mod
from ..project import journal_dir

import json

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

MANAGED_START = "<!-- conductor:managed:start"
MANAGED_END = "<!-- conductor:managed:end -->"
MEMORY_KINDS = ("decision", "solution", "error", "plan")
MEMORY_LIMIT = 15


@dataclass
class GuideContext:
    """Everything a target needs to render/splice the project guide."""
    root: Path
    slug: str
    ptype: str
    selected: List[str]


# --- shared guide rendering (CLAUDE.md and AGENTS.md share the same body) -----

def roles_table(selected: List[str]) -> str:
    rows = ["| Role | Area | Skill |", "|------|------|-------|"]
    for slug in selected:
        r = roles_mod.ROLES[slug]
        rows.append(f"| `{slug}` | {r.area} | `{r.skill}` |")
    return "\n".join(rows)


def project_memory(root: Path, limit: int = MEMORY_LIMIT) -> str:
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


def render_guide(ctx: GuideContext, template: str = "CLAUDE.md.tmpl") -> str:
    """Render a project guide from `templates/<template>` + the shared flow."""
    tmpl = (TEMPLATES / template).read_text(encoding="utf-8")
    flow = (TEMPLATES / "flow.md").read_text(encoding="utf-8")
    return (tmpl
            .replace("{project}", ctx.slug)
            .replace("{type}", ctx.ptype)
            .replace("{roles_table}", roles_table(ctx.selected))
            .replace("{project_memory}", project_memory(ctx.root))
            .replace("{flow}", flow))


def _managed_slice(text: str) -> Optional[Tuple[int, int]]:
    """(start, end) spanning the managed region (incl markers), or None."""
    s = text.find(MANAGED_START)
    e = text.find(MANAGED_END)
    if s == -1 or e == -1:
        return None
    return s, e + len(MANAGED_END)


def write_guide(path: Path, ctx: GuideContext, template: str = "CLAUDE.md.tmpl") -> str:
    """Write (init) or splice (sync) the guide. Returns 'created' or 'synced'.

    On sync, only the managed region is replaced; anything the human wrote below
    the end marker is preserved.
    """
    fresh = render_guide(ctx, template)
    if path.is_file():
        old = path.read_text(encoding="utf-8")
        old_span, new_span = _managed_slice(old), _managed_slice(fresh)
        if old_span and new_span:
            region = fresh[new_span[0]:new_span[1]]
            merged = old[:old_span[0]] + region + old[old_span[1]:]
            path.write_text(merged, encoding="utf-8")
            return "synced"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fresh, encoding="utf-8")
    return "created"


# --- frontmatter helpers (targets translate the dialect) ---------------------

def split_frontmatter(md: str) -> Tuple[Dict[str, str], str]:
    """Split a `--- key: value --- body` template into ({key: raw_value}, body).

    Deliberately minimal: the role/skill templates are flat `key: value` blocks
    (R2/R3 guarantee `name`/`description`, the latter double-quoted on one line).
    Values are returned verbatim (quotes intact); the caller decides how to
    re-emit them. Returns ({}, md) when there is no frontmatter.
    """
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end == -1:
        return {}, md
    block = md[3:end].strip("\n")
    body = md[end + 4:].lstrip("\n")
    meta: Dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta, body


def merge_role_skill(role_slug: str) -> Optional[Tuple[str, str, str]]:
    """Fold a role's agent persona into its skill, for harnesses with no
    subagents (Codex, Pi) where a **skill** is the native delegation surface.

    Returns (skill_slug, description, body) where body is the agent system
    prompt + a model-tier hint + the skill's When-to-use/Steps. The skill's own
    description is used (it is phrased "Use to …", ideal for implicit matching).
    Returns None if either template is missing.
    """
    skill_slug = roles_mod.ROLES[role_slug].skill
    agent_src = TEMPLATES / "agents" / f"{role_slug}.md"
    skill_src = TEMPLATES / "skills" / skill_slug / "SKILL.md"
    if not agent_src.is_file() or not skill_src.is_file():
        return None
    agent_meta, agent_body = split_frontmatter(agent_src.read_text(encoding="utf-8"))
    skill_meta, skill_body = split_frontmatter(skill_src.read_text(encoding="utf-8"))
    description = skill_meta.get("description", agent_meta.get("description", '""'))
    tier = agent_meta.get("model", "").strip()
    tier_line = f"**Model tier (run on this if your harness can switch):** {tier}\n\n" if tier else ""
    body = f"{tier_line}{agent_body.rstrip()}\n\n---\n\n{skill_body.lstrip()}"
    return skill_slug, description, body


def join_frontmatter(meta: Dict[str, str], body: str) -> str:
    """Inverse of split_frontmatter: emit `--- key: value --- \\n body`.

    Values are written verbatim — the caller is responsible for quoting (so a
    description already wrapped in double quotes round-trips unchanged).
    """
    lines = ["---"]
    for key, val in meta.items():
        lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.lstrip("\n")


# --- the Target contract -----------------------------------------------------

class Target(Protocol):
    key: str       # stable id used by `--target` and `.cdt/config.json`
    label: str     # human name for CLI output

    def detect(self, project: Path) -> bool:
        """True when this harness is already used in `project` (for auto-detect)."""
        ...

    def guide_path(self, project: Path) -> Path:
        """Path of this target's project guide (e.g. CLAUDE.md / AGENTS.md)."""
        ...

    def emit_roles(self, project: Path, selected: List[str]) -> int:
        """Project the selected roles into the harness's native layout. Returns count."""
        ...

    def emit_driver(self, project: Path) -> bool:
        """Install the `/cdt` flow driver. Returns True if written."""
        ...

    def emit_hooks(self, project: Path) -> int:
        """Wire the live-memory (Honcho) capture/inject hooks. Returns count added."""
        ...

    def emit_guide(self, ctx: GuideContext) -> str:
        """Write/splice the project guide. Returns 'created' or 'synced'."""
        ...
