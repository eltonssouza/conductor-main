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


def _emit_intake_skill(skills_root: Path) -> None:
    """Write the /cdt-intake command as a Codex skill ($cdt-intake)."""
    res = base.command_as_skill("intake", "cdt-intake")
    if res is None:
        return
    name, description, body = res
    dst = skills_root / "cdt-intake"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "SKILL.md").write_text(
        base.join_frontmatter({"name": name, "description": description}, body),
        encoding="utf-8",
    )


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
        _emit_intake_skill(project.joinpath(*SKILLS_REL))
        return True

    def emit_hooks(self, project: Path) -> int:
        return 0  # Codex has no prompt-capture event to bind live memory to

    def emit_automations(self, project: Path) -> int:
        text = base.automation_text("triage")
        if text is None:
            return 0
        dst = project.joinpath(*SKILLS_REL, "cdt-triage")
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "SKILL.md").write_text(text, encoding="utf-8")
        return 1

    def emit_mcp(self, project: Path) -> int:
        """Register MCP connectors in Codex's `.codex/config.toml`.

        Hand-writes minimal TOML (`[mcp_servers.<name>]` blocks) — stdlib has no
        TOML writer. `conductor` is an active block; the disabled third-party
        connectors are emitted as commented-out blocks (each line prefixed `# `)
        so they don't auto-start — the user uncomments and fills the env to wire
        one in. Idempotent: a simple substring guard skips appending when an
        active `[mcp_servers.conductor]` block already exists.
        """
        cfg = project / ".codex" / "config.toml"
        existing = cfg.read_text(encoding="utf-8") if cfg.is_file() else ""
        if "[mcp_servers.conductor]" in existing:
            return 0  # already wired in — don't duplicate

        blocks = []
        for name, c in base.CONNECTORS.items():
            block = self._toml_block(name, c)
            if not c.get("enabled"):
                block = "\n".join(("# " + ln if ln else "#") for ln in block.splitlines())
            blocks.append(block)
        addition = "\n\n".join(blocks) + "\n"
        text = (existing.rstrip("\n") + "\n\n" + addition) if existing.strip() else addition

        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(text, encoding="utf-8")
        return 1

    @staticmethod
    def _toml_block(name: str, c: dict) -> str:
        def quote(s: str) -> str:
            return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'

        args = ", ".join(quote(a) for a in c["args"])
        lines = [f"[mcp_servers.{name}]",
                 f"command = {quote(c['command'])}",
                 f"args = [{args}]"]
        env = c.get("env") or {}
        if env:
            lines.append(f"[mcp_servers.{name}.env]")
            lines.extend(f"{k} = {quote(v)}" for k, v in env.items())
        return "\n".join(lines)

    def emit_guide(self, ctx: GuideContext) -> str:
        return base.write_guide(ctx.root / "AGENTS.md", ctx, "AGENTS.md.tmpl")
