"""Claude Code target — the original layout, extracted verbatim.

Projects into:
  .claude/agents/<role>.md          role Agents (copied as-is)
  .claude/skills/<skill>/SKILL.md   matching Skills
  .claude/commands/cdt.md           the `/cdt` flow driver
  .claude/settings.local.json       Honcho capture/inject hooks (machine-local)
  CLAUDE.md                         the project guide
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List

from .. import roles as roles_mod
from . import base
from .base import GuideContext, TEMPLATES

# Claude Code hooks that make Honcho a live memory: capture the owner's prompts
# and inject Honcho's recollection at session start. Written to machine-local
# settings, so collaborators without `cdt` are unaffected.
HONCHO_HOOKS = {
    "UserPromptSubmit": "cdt journal observe",
    "SessionStart": "cdt journal context",
}


class ClaudeTarget:
    key = "claude"
    label = "Claude Code"

    def detect(self, project: Path) -> bool:
        return (project / ".claude").is_dir() or (project / "CLAUDE.md").is_file()

    def guide_path(self, project: Path) -> Path:
        return project / "CLAUDE.md"

    def emit_roles(self, project: Path, selected: List[str]) -> int:
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

    def emit_driver(self, project: Path) -> bool:
        src = TEMPLATES / "commands" / "cdt.md"
        if not src.is_file():
            return False
        dst = project / ".claude" / "commands"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst / "cdt.md")
        intake = TEMPLATES / "commands" / "intake.md"
        if intake.is_file():
            shutil.copyfile(intake, dst / "cdt-intake.md")
        return True

    def emit_hooks(self, project: Path) -> int:
        sp = project / ".claude" / "settings.local.json"
        data: dict = {}
        if sp.is_file():
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
        if not isinstance(data, dict):
            data = {}
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            return 0
        added = 0
        for event, command in HONCHO_HOOKS.items():
            entries = hooks.setdefault(event, [])
            if not isinstance(entries, list):
                continue
            present = any(
                any(command in (h.get("command", "") or "")
                    for h in (e.get("hooks") or []) if isinstance(h, dict))
                for e in entries if isinstance(e, dict))
            if not present:
                entries.append({"hooks": [{"type": "command", "command": command}]})
                added += 1
        if added:
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        return added

    def emit_automations(self, project: Path) -> int:
        text = base.automation_text("triage")
        if text is None:
            return 0
        dst = project / ".claude" / "commands"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "cdt-triage.md").write_text(text, encoding="utf-8")
        return 1

    def emit_mcp(self, project: Path) -> int:
        """Register MCP connectors in Claude Code's native `.mcp.json` (project root).

        Claude's format has no `enabled` flag, so only enabled connectors (just
        `conductor`) land in `.mcp.json` — merged into any existing `mcpServers`
        without disturbing other keys or servers. The disabled third-party stubs
        are written to a companion `.mcp.connectors.example.json` (same shape) the
        user can copy entries from. Both files are counted.
        """
        written = 0
        active = {name: {"command": c["command"], "args": c["args"], "env": c["env"]}
                  for name, c in base.CONNECTORS.items() if c.get("enabled")}
        stubs = {name: {"command": c["command"], "args": c["args"], "env": c["env"]}
                 for name, c in base.CONNECTORS.items() if not c.get("enabled")}

        mp = project / ".mcp.json"
        data: dict = {}
        if mp.is_file():
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
        if not isinstance(data, dict):
            data = {}
        servers = data.setdefault("mcpServers", {})
        if isinstance(servers, dict):
            added = False
            for name, spec in active.items():
                if name not in servers:           # add only if absent (merge-not-clobber)
                    servers[name] = spec
                    added = True
            if added or not mp.is_file():
                mp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
                written += 1

        ex = project / ".mcp.connectors.example.json"
        ex.write_text(json.dumps({"mcpServers": stubs}, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
        written += 1
        return written

    def emit_guide(self, ctx: GuideContext) -> str:
        return base.write_guide(ctx.root / "CLAUDE.md", ctx, "CLAUDE.md.tmpl")
