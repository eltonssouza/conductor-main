"""`cdt odysseus install` — install Conductor into an Odysseus workspace's Brain.

Unlike `cdt init` (which scaffolds per-project config into each repo), this
command installs **all** Conductor skills **once** into the Odysseus "Brain"
(`data/skills/conductor/`), globally. Every chat/project inside Odysseus then
sees the 36 roles + the `/cdt` flow driver + the `cdt-triage` automation, with
no per-project enrollment.

It also wires the Odysseus agent's access to an external host folder (so it can
work on real projects): a non-invasive `docker-compose.override.yml` bind-mount
plus a patch to `data/settings.json` (`tool_path_extra_roots`).

Reuses the OdysseusTarget emitters (which already stamp the frontmatter Odysseus
needs: `status: published` + `owner` + `category: conductor`). Skips the
per-project guide, the project registry, the `.cdt/` memory tree, and MCP
(MCP is phase 2 — it needs Conductor installed inside the container + backends).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .roles import select_roles
from .targets.odysseus import OdysseusTarget, _is_odysseus, _resolve_owner

# Marker so we only ever rewrite an override file that we authored — never
# clobber one a human wrote by hand.
_OVERRIDE_MARKER = "# Managed by `cdt odysseus install` — Conductor external workspace mounts."
_DEFAULT_MOUNT = "/workspace"


def _detect_from_docker() -> Optional[Path]:
    """Auto-detect the Odysseus host dir from a running container.

    Odysseus usually runs via Docker Compose, so a live container carries the
    host directory it was launched from in the `com.docker.compose.project
    .working_dir` label. We read every running container's label and return the
    first whose dir looks like an Odysseus install (`_is_odysseus`) — so
    `cdt odysseus install --projects …` works from anywhere, no --home needed.
    """
    if not shutil.which("docker"):
        return None
    try:
        out = subprocess.run(
            ["docker", "ps", "--format",
             '{{.Label "com.docker.compose.project.working_dir"}}'],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    seen: set = set()
    for line in out.splitlines():
        d = line.strip()
        if not d or d in seen:
            continue
        seen.add(d)
        root = Path(d)
        if _is_odysseus(root):
            return root
    return None


def _resolve_root(home: Optional[str]) -> Optional[Path]:
    """Locate the Odysseus install: --home → $ODYSSEUS_HOME → cwd → running container."""
    cand = home or os.environ.get("ODYSSEUS_HOME")
    if cand:
        root = Path(cand).expanduser()
        return root if _is_odysseus(root) else None
    cwd = Path.cwd()
    if _is_odysseus(cwd):
        return cwd
    return _detect_from_docker()


# --- docker-compose.override.yml (bind-mount the external host folder) --------

def _existing_mounts(text: str) -> List[tuple]:
    """Pull (source, target) pairs out of an override file we previously wrote."""
    pairs = []
    for m in re.finditer(r"source:\s*(.+?)\s*\n\s*target:\s*(.+?)\s*(?:\n|$)", text):
        pairs.append((m.group(1).strip(), m.group(2).strip()))
    return pairs


def _render_override(mounts: List[tuple]) -> str:
    lines = [
        _OVERRIDE_MARKER,
        "# Docker Compose merges this with docker-compose.yml automatically;",
        "# the original compose file is left untouched.",
        "services:",
        "  odysseus:",
        "    volumes:",
    ]
    for source, target in mounts:
        lines += ["      - type: bind",
                  f"        source: {source}",
                  f"        target: {target}"]
    return "\n".join(lines) + "\n"


def _write_compose_override(root: Path, mounts: List[tuple]) -> str:
    """Write docker-compose.override.yml with the given bind-mounts (merged with
    any we wrote before). Returns 'created', 'updated', 'exists', or 'skipped'.
    """
    path = root / "docker-compose.override.yml"
    desired = list(mounts)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if _OVERRIDE_MARKER not in text:
            print(f"[odysseus] {path.name} exists and was not written by Conductor; "
                  f"not touching it. Add the mounts manually.", file=sys.stderr)
            return "skipped"
        for m in _existing_mounts(text):       # merge prior mounts (dedup)
            if m not in desired:
                desired.insert(0, m)
        new = _render_override(desired)
        if new == text:
            return "exists"
        path.write_text(new, encoding="utf-8")
        return "updated"
    path.write_text(_render_override(desired), encoding="utf-8")
    return "created"


def _seed_mcp_http(root: Path, url: str) -> str:
    """Seed/replace the `conductor` MCP server row pointing at the standalone
    Conductor MCP server (streamable-http; see infra/mcp/). Returns 'seeded' or
    a short error string."""
    import sqlite3
    db = root / "data" / "app.db"
    if not db.is_file():
        return "no app.db (start Odysseus once first)"
    now = _utcnow()
    try:
        con = sqlite3.connect(str(db))
        with con:
            con.execute(
                """INSERT OR REPLACE INTO mcp_servers
                   (id, name, transport, command, args, env, url, is_enabled,
                    created_at, updated_at)
                   VALUES ('conductor','conductor','http',NULL,NULL,'{}',?,1,?,?)""",
                (url, now, now))
        con.close()
        return "seeded"
    except sqlite3.Error as e:
        return f"db error: {e}"


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


# --- data/settings.json patch (tool_path_extra_roots) ------------------------

def _atomic_write_json(path: Path, data: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _patch_extra_roots(root: Path, mount: str) -> str:
    """Add `mount` to `tool_path_extra_roots` in data/settings.json.

    Returns 'added', 'exists', or 'created' (file was absent).
    """
    path = root / "data" / "settings.json"
    if path.is_file():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
        created = False
    else:
        settings = {}
        created = True
    if not isinstance(settings, dict):
        settings = {}
    roots = settings.get("tool_path_extra_roots")
    if not isinstance(roots, list):
        roots = []
    if mount in roots:
        return "exists"
    roots.append(mount)
    settings["tool_path_extra_roots"] = roots
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, settings)
    return "created" if created else "added"


# --- command entry point -----------------------------------------------------

def _doctor(root: Path) -> int:
    """Validate a Conductor↔Odysseus install without changing anything.

    Checks the things that silently break the integration: skills present and
    framed so Odysseus surfaces them (published + owned + category), the MCP row,
    and the Docker/settings wiring. Returns 0 if no problems, else 1.
    """
    import sqlite3
    problems = 0

    def ok(msg): print(f"  [OK  ] {msg}")
    def warn(msg):
        nonlocal problems
        problems += 1
        print(f"  [WARN] {msg}")

    print(f"Odysseus doctor — {root}")

    sk = root / "data" / "skills" / "conductor"
    skills = sorted(sk.glob("*/SKILL.md")) if sk.is_dir() else []
    if not skills:
        warn("no Conductor skills in data/skills/conductor — run `cdt odysseus install`")
    else:
        ok(f"{len(skills)} Conductor skills on disk")
        sample = skills[0].read_text(encoding="utf-8")
        for need in ("status: published", "category: conductor", "owner:"):
            if need not in sample:
                warn(f"sample skill {skills[0].parent.name} missing '{need}' "
                     f"(Odysseus would hide it)")
        if all(n in sample for n in ("status: published", "category: conductor", "owner:")):
            ok("skill frontmatter is surfaceable (published + owner + category)")

    db = root / "data" / "app.db"
    if not db.is_file():
        warn("data/app.db absent (start Odysseus once) — MCP cannot be seeded")
    else:
        try:
            con = sqlite3.connect(str(db))
            rows = list(con.execute(
                "SELECT transport, is_enabled FROM mcp_servers WHERE id='conductor'"))
            con.close()
            if rows:
                ok(f"MCP row present (transport={rows[0][0]}, enabled={rows[0][1]})")
            else:
                print("  [info] no Conductor MCP row (optional; add with --with-mcp)")
        except sqlite3.Error as e:
            warn(f"cannot read mcp_servers: {e}")

    ov = root / "docker-compose.override.yml"
    if ov.is_file() and _OVERRIDE_MARKER in ov.read_text(encoding="utf-8"):
        ok("docker-compose.override.yml present (Conductor-managed)")
    else:
        warn("no Conductor docker-compose.override.yml (agent lacks host-folder access)")

    sj = root / "data" / "settings.json"
    try:
        roots = json.loads(sj.read_text(encoding="utf-8")).get("tool_path_extra_roots")
        if roots:
            ok(f"tool_path_extra_roots = {roots}")
        else:
            warn("tool_path_extra_roots empty (agent file tools confined to data/)")
    except (OSError, ValueError):
        warn("data/settings.json unreadable")

    print("OK" if problems == 0 else f"{problems} warning(s)")
    return 0 if problems == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cdt odysseus",
        description="Integrate Conductor with an Odysseus workspace (global Brain).",
    )
    parser.add_argument("action", choices=["install", "doctor"], help="what to do")
    parser.add_argument("--projects", metavar="HOST_PATH", nargs="+",
                        help="host folder(s) to expose to the agent workspace (install)")
    parser.add_argument("--home", metavar="ODYSSEUS_HOME",
                        help="Odysseus install dir (else $ODYSSEUS_HOME or auto-detect)")
    parser.add_argument("--mount", metavar="CONTAINER_PATH", default=_DEFAULT_MOUNT,
                        help=f"container mount root (default {_DEFAULT_MOUNT}; with several "
                             "--projects, each lands at <mount>/<basename>)")
    parser.add_argument("--owner", metavar="USER",
                        help="Brain owner for the skills (else from data/auth.json)")
    parser.add_argument("--with-mcp", action="store_true", dest="with_mcp",
                        help="also register the standalone Conductor MCP server "
                             "(run it from infra/mcp/) in Odysseus's MCP servers")
    parser.add_argument("--mcp-url", default="http://host.docker.internal:8808/mcp",
                        help="URL of the running Conductor MCP server "
                             "(default http://host.docker.internal:8808/mcp)")
    args = parser.parse_args(argv)

    root = _resolve_root(args.home)
    if root is None:
        print("[odysseus] Odysseus install not found. With Odysseus running in "
              "Docker it is auto-detected; otherwise run from the Odysseus dir, "
              "set ODYSSEUS_HOME, or pass --home <path>.", file=sys.stderr)
        return 2

    if args.action == "doctor":
        return _doctor(root)

    # install
    if not args.projects:
        print("[odysseus] install needs --projects <host folder> [more...]", file=sys.stderr)
        return 2
    hosts = [Path(p).expanduser() for p in args.projects]
    for h in hosts:
        if not h.is_dir():
            print(f"[odysseus] --projects folder does not exist: {h}", file=sys.stderr)
            return 2
    base_mount = args.mount.rstrip("/") or "/workspace"
    mounts = [(str(h), base_mount if len(hosts) == 1 else f"{base_mount}/{h.name}")
              for h in hosts]

    os.environ["ODYSSEUS_HOME"] = str(root)
    if args.owner:
        os.environ["ODYSSEUS_OWNER"] = args.owner

    target = OdysseusTarget()
    n_roles = target.emit_roles(root, select_roles("unknown", all_roles=True))
    driver_ok = target.emit_driver(root)
    n_autos = target.emit_automations(root)

    override_state = _write_compose_override(root, mounts)
    settings_states = {m: _patch_extra_roots(root, m) for _, m in mounts}
    mcp_state = _seed_mcp_http(root, args.mcp_url) if args.with_mcp else None

    owner = _resolve_owner(root)
    print(f"Conductor -> Odysseus Brain at {root}")
    print(f"  skills:   {n_roles} roles"
          f"{' + cdt driver + cdt-intake' if driver_ok else ''}"
          f"{f' + {n_autos} automation(s)' if n_autos else ''}"
          f"  (owner={owner or 'none'}, status=published, category=conductor)")
    print(f"  docker:   docker-compose.override.yml {override_state}")
    for src, m in mounts:
        print(f"            mount {src} -> {m}  (extra_roots: {settings_states[m]})")
    if args.with_mcp:
        print(f"  mcp:      registered '{args.mcp_url}' (http) — db {mcp_state}")
    print()
    print("Next: restart Odysseus so it picks up the mounts + skills:")
    print(f"    cd {root} && docker compose up -d")
    if args.with_mcp:
        print("Also start the Conductor MCP server it points at:")
        print("    cd infra/mcp && docker compose up -d --build   (and `cdt up` for the RAG backend)")
    print("Then open an agent-mode chat — the Conductor roles + /cdt + /cdt-intake "
          "appear in the skills index; the agent can read/write the mounted folder(s).")
    print("Tip: `cdt odysseus doctor` re-checks this install at any time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
