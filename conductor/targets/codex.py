"""Codex CLI target — roles as native skills + AGENTS.md guide.

Codex has no auto-invoked subagents and no per-agent model tier, so a role's
expert lens is delivered as a **skill** (folded persona + steps). Projects into:
  .agents/skills/<skill>/SKILL.md    role skills (persona + steps), `$skill`-invokable
  .agents/skills/cdt/SKILL.md        the `/cdt` flow driver, as a skill ($cdt)
  AGENTS.md                          the project guide

`.agents/skills/` is Codex's project skill path (scanned cwd → repo root). No
live-memory hook: Codex exposes no prompt-capture event, so `cdt journal observe`
has nothing to bind to here (recall is still available on demand via `cdt`).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from . import base
from .base import GuideContext, TEMPLATES

SKILLS_REL = (".agents", "skills")


class CodexTarget:
    key = "codex"
    label = "Codex"

    def detect(self, project: Path) -> bool:
        return ((project / ".codex").is_dir()
                or (project / ".codex" / "config.toml").is_file())

    def guide_path(self, project: Path) -> Path:
        return project / "AGENTS.md"

    def emit_roles(self, project: Path, selected: List[str]) -> int:
        skills_dst = project.joinpath(*SKILLS_REL)
        skills_dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for slug in selected:
            merged = base.merge_role_skill(slug)
            if merged is None:
                continue
            skill_slug, description, body = merged
            (skills_dst / skill_slug).mkdir(parents=True, exist_ok=True)
            (skills_dst / skill_slug / "SKILL.md").write_text(
                base.join_frontmatter({"name": skill_slug, "description": description}, body),
                encoding="utf-8")
            n += 1
        return n

    def emit_driver(self, project: Path) -> bool:
        src = TEMPLATES / "commands" / "cdt.codex.md"
        if not src.is_file():
            return False
        dst = project.joinpath(*SKILLS_REL, "cdt")
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst / "SKILL.md")
        return True

    def emit_hooks(self, project: Path) -> int:
        return 0  # Codex has no prompt-capture event to bind live memory to

    def emit_guide(self, ctx: GuideContext) -> str:
        return base.write_guide(ctx.root / "AGENTS.md", ctx, "AGENTS.md.tmpl")
