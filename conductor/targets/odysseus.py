"""Odysseus target — conductor roles as skills + SQLite MCP registration.

Odysseus is a standalone AI workspace (web server); skills land in
data/skills/conductor/<slug>/SKILL.md (the "conductor" category in Odysseus).
There are no harness hooks (Odysseus has no prompt-capture event). The conductor
MCP server is seeded directly into data/app.db because Odysseus stores MCP
servers in SQLite — there is no static config file.

Resolution order for the Odysseus root:
  1. ODYSSEUS_HOME env var — set this when running `cdt init` from a project dir.
  2. Project dir itself — when running `cdt init` from inside the Odysseus dir.

When neither is available (e.g. `--target all` on an unrelated project) every
emit method returns 0 / False and prints a one-line hint to stderr.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import base
from .base import GuideContext, TEMPLATES, _managed_slice

SKILLS_REL = ("data", "skills", "conductor")  # Odysseus category = "conductor"


def _is_odysseus(path: Path) -> bool:
    return (path / "data" / "skills").is_dir() and (path / "app.py").is_file()


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


def _resolve_owner(root: Path) -> Optional[str]:
    """The Odysseus username that should own the emitted skills.

    Odysseus surfaces skills to the agent via SkillsManager.index_for(owner=...),
    which strict-filters by owner (effective_user). An ownerless skill is hidden
    from every authenticated user, so the persona/flow would land on disk but
    never reach the agent. Resolution order:

      1. ODYSSEUS_OWNER env var (explicit override).
      2. data/auth.json — the lone admin, else the lone user, else first admin.
      3. None (acceptable only for an auth-less single-user deployment).
    """
    env = os.environ.get("ODYSSEUS_OWNER")
    if env:
        return env
    try:
        users = json.loads((root / "data" / "auth.json").read_text(encoding="utf-8")).get("users", {})
    except (OSError, ValueError):
        return None
    if not isinstance(users, dict) or not users:
        return None
    admins = [u for u, v in users.items() if isinstance(v, dict) and v.get("is_admin")]
    if len(admins) == 1:
        return admins[0]
    if len(users) == 1:
        return next(iter(users))
    return admins[0] if admins else None


def _skill_frontmatter(name: str, description: str, owner: Optional[str]) -> dict:
    """Frontmatter Odysseus needs so an emitted skill actually surfaces to the
    agent: `status: published` (drafts are excluded from the prompt index),
    `category: conductor` (else it defaults to general and the file is relocated
    on any rewrite), and `owner` (else the strict owner filter hides it).

    `description` is passed through verbatim (already double-quoted by the
    templates); join_frontmatter does not re-quote.
    """
    meta = {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "category": "conductor",
        "status": "published",
        "source": "imported",
        "confidence": "0.9",
    }
    if owner:
        meta["owner"] = owner
    return meta


class OdysseusTarget:
    key = "odysseus"
    label = "Odysseus"

    def detect(self, project: Path) -> bool:
        if os.environ.get("ODYSSEUS_HOME"):
            return True
        return _is_odysseus(project)

    def guide_path(self, project: Path) -> Path:
        root = self._root(project)
        if root is None:
            return project / "AGENTS.md"
        return root.joinpath(*SKILLS_REL, "guide", "SKILL.md")

    # ------------------------------------------------------------------ internals

    def _root(self, project: Path) -> Optional[Path]:
        env = os.environ.get("ODYSSEUS_HOME")
        if env:
            return Path(env)
        if _is_odysseus(project):
            return project
        return None

    def _skills_dir(self, project: Path) -> Optional[Path]:
        root = self._root(project)
        return root.joinpath(*SKILLS_REL) if root is not None else None

    def _warn_no_root(self) -> None:
        print(
            "[conductor:odysseus] Cannot locate Odysseus. "
            "Set ODYSSEUS_HOME=<path> or run `cdt init` from the Odysseus directory.",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------ emit API

    def emit_roles(self, project: Path, selected: List[str]) -> int:
        skills_dir = self._skills_dir(project)
        if skills_dir is None:
            self._warn_no_root()
            return 0
        owner = _resolve_owner(self._root(project))
        n = 0
        for slug in selected:
            merged = base.merge_role_skill(slug)
            if merged is None:
                continue
            skill_slug, description, body = merged
            dest = skills_dir / skill_slug
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                base.join_frontmatter(_skill_frontmatter(skill_slug, description, owner), body),
                encoding="utf-8",
            )
            n += 1
        return n

    def emit_driver(self, project: Path) -> bool:
        skills_dir = self._skills_dir(project)
        if skills_dir is None:
            return False
        src = TEMPLATES / "commands" / "cdt.odysseus.md"
        if not src.is_file():
            src = TEMPLATES / "commands" / "cdt.codex.md"
        if not src.is_file():
            return False
        meta, body = base.split_frontmatter(src.read_text(encoding="utf-8"))
        owner = _resolve_owner(self._root(project))
        fm = _skill_frontmatter(
            meta.get("name", "cdt"),
            meta.get("description", '"Conductor flow driver — runs a demand through the 11 gates."'),
            owner,
        )
        dst = skills_dir / "cdt"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "SKILL.md").write_text(base.join_frontmatter(fm, body), encoding="utf-8")
        return True

    def emit_hooks(self, project: Path) -> int:
        return 0  # Odysseus has no prompt-capture event for live-memory binding

    def emit_automations(self, project: Path) -> int:
        skills_dir = self._skills_dir(project)
        if skills_dir is None:
            return 0
        text = base.automation_text("triage")
        if text is None:
            return 0
        meta, body = base.split_frontmatter(text)
        owner = _resolve_owner(self._root(project))
        fm = _skill_frontmatter(
            meta.get("name", "cdt-triage"),
            meta.get("description", '"Autonomous discovery → maker → checker triage loop."'),
            owner,
        )
        dst = skills_dir / "cdt-triage"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "SKILL.md").write_text(base.join_frontmatter(fm, body), encoding="utf-8")
        return 1

    def emit_mcp(self, project: Path) -> int:
        """Seed the Conductor MCP server into Odysseus's data/app.db.

        Odysseus keeps MCP server config in SQLite (no static file). Inserts a
        `conductor` stdio row. Uses INSERT OR IGNORE — idempotent on re-runs.
        Falls back to a guide skill when the DB doesn't exist yet.
        """
        root = self._root(project)
        if root is None:
            return 0
        db_path = root / "data" / "app.db"
        if db_path.is_file():
            return self._seed_mcp_db(db_path)
        return self._write_mcp_guide(root)

    def _seed_mcp_db(self, db_path: Path) -> int:
        c = base.CONNECTORS["conductor"]
        now = _utcnow_str()
        try:
            con = sqlite3.connect(str(db_path))
            with con:
                con.execute(
                    """
                    INSERT OR IGNORE INTO mcp_servers
                        (id, name, transport, command, args, env,
                         url, is_enabled, created_at, updated_at)
                    VALUES (?, ?, 'stdio', ?, ?, '{}', NULL, 1, ?, ?)
                    """,
                    ("conductor", "conductor", c["command"],
                     json.dumps(c["args"]), now, now),
                )
            con.close()
            return 1
        except sqlite3.Error as exc:
            print(
                f"[conductor:odysseus] MCP DB seed failed ({exc}); writing setup guide instead.",
                file=sys.stderr,
            )
            return self._write_mcp_guide(db_path.parent.parent)

    def _write_mcp_guide(self, odysseus_root: Path) -> int:
        c = base.CONNECTORS["conductor"]
        cmd = " ".join([c["command"]] + c["args"])
        content = base.join_frontmatter(
            _skill_frontmatter(
                "conductor-mcp",
                '"Setup guide: add the Conductor MCP server (library RAG + journal) to Odysseus."',
                _resolve_owner(odysseus_root),
            ),
            f"""# Conductor MCP Setup

Odysseus's database is not initialised yet (start Odysseus once first).

Once running, go to **Settings → Admin → MCP Servers** and add:

| Field     | Value       |
|-----------|-------------|
| Name      | `conductor` |
| Transport | stdio       |
| Command   | `{cmd}`     |

Once connected, Odysseus agents gain `library_search`, `journal_recall`, and
`journal_add` tools — the project's RAG library and decision journal.
""",
        )
        skills_dir = odysseus_root.joinpath(*SKILLS_REL)
        dst = skills_dir / "conductor-mcp"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "SKILL.md").write_text(content, encoding="utf-8")
        return 1

    def emit_guide(self, ctx: GuideContext) -> str:
        """Write the project guide as an Odysseus conductor skill.

        The skill's frontmatter is preserved across syncs; only the managed
        region inside the body is replaced (same splice logic as base.write_guide).
        """
        root = self._root(ctx.root)
        if root is None:
            return "created"
        path = root.joinpath(*SKILLS_REL, "guide", "SKILL.md")
        rendered = base.render_guide(ctx, "AGENTS.md.tmpl")
        description = (
            f'"Conductor project guide — roles, 11-gate flow, '
            f'and project memory for {ctx.slug}."'
        )
        if path.is_file():
            old = path.read_text(encoding="utf-8")
            old_span = _managed_slice(old)
            new_span = _managed_slice(rendered)
            if old_span and new_span:
                region = rendered[new_span[0]:new_span[1]]
                merged = old[:old_span[0]] + region + old[old_span[1]:]
                path.write_text(merged, encoding="utf-8")
                return "synced"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            base.join_frontmatter(
                _skill_frontmatter("conductor-guide", description, _resolve_owner(root)),
                rendered,
            ),
            encoding="utf-8",
        )
        return "created"
