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
import sys
from pathlib import Path
from typing import List, Optional

from .roles import select_roles
from .targets.odysseus import OdysseusTarget, _is_odysseus, _resolve_owner

# Marker so we only ever rewrite an override file that we authored — never
# clobber one a human wrote by hand.
_OVERRIDE_MARKER = "# Managed by `cdt odysseus install` — Conductor external workspace mounts."
_DEFAULT_MOUNT = "/workspace"


def _resolve_root(home: Optional[str]) -> Optional[Path]:
    """Locate the Odysseus install: --home → $ODYSSEUS_HOME → cwd auto-detect."""
    cand = home or os.environ.get("ODYSSEUS_HOME")
    if cand:
        root = Path(cand).expanduser()
        return root if _is_odysseus(root) else None
    cwd = Path.cwd()
    return cwd if _is_odysseus(cwd) else None


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
        lines += [
            "      - type: bind",
            f"        source: {source}",
            f"        target: {target}",
        ]
    return "\n".join(lines) + "\n"


def _write_compose_override(root: Path, host: Path, mount: str) -> str:
    """Add a bind-mount of `host` → `mount` to docker-compose.override.yml.

    Returns one of: 'created', 'updated', 'exists' (already present), or
    'skipped' (a non-managed override file is in the way).
    """
    path = root / "docker-compose.override.yml"
    source = str(host)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if _OVERRIDE_MARKER not in text:
            print(
                f"[odysseus] {path.name} exists and was not written by Conductor; "
                f"not touching it. Add this bind-mount manually:\n"
                f"    {source} -> {mount}",
                file=sys.stderr,
            )
            return "skipped"
        mounts = _existing_mounts(text)
        if (source, mount) in mounts:
            return "exists"
        mounts.append((source, mount))
        path.write_text(_render_override(mounts), encoding="utf-8")
        return "updated"
    path.write_text(_render_override([(source, mount)]), encoding="utf-8")
    return "created"


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

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cdt odysseus install",
        description="Install all Conductor skills into an Odysseus Brain (global).",
    )
    parser.add_argument("action", choices=["install"], help="what to do")
    parser.add_argument("--projects", metavar="HOST_PATH", required=True,
                        help="host folder to expose to the Odysseus agent workspace")
    parser.add_argument("--home", metavar="ODYSSEUS_HOME",
                        help="Odysseus install dir (else $ODYSSEUS_HOME or auto-detect)")
    parser.add_argument("--mount", metavar="CONTAINER_PATH", default=_DEFAULT_MOUNT,
                        help=f"where the host folder lands in the container (default {_DEFAULT_MOUNT})")
    parser.add_argument("--owner", metavar="USER",
                        help="Brain owner for the skills (else from data/auth.json)")
    args = parser.parse_args(argv)

    root = _resolve_root(args.home)
    if root is None:
        print(
            "[odysseus] Odysseus install not found. Run from the Odysseus dir, "
            "set ODYSSEUS_HOME, or pass --home <path>.",
            file=sys.stderr,
        )
        return 2

    host = Path(args.projects).expanduser()
    if not host.is_dir():
        print(f"[odysseus] --projects folder does not exist: {host}", file=sys.stderr)
        return 2

    # Reuse the OdysseusTarget emitters via their env-based root/owner resolution.
    os.environ["ODYSSEUS_HOME"] = str(root)
    if args.owner:
        os.environ["ODYSSEUS_OWNER"] = args.owner

    target = OdysseusTarget()
    all_slugs = select_roles("unknown", all_roles=True)
    n_roles = target.emit_roles(root, all_slugs)
    driver_ok = target.emit_driver(root)
    n_autos = target.emit_automations(root)

    override_state = _write_compose_override(root, host, args.mount)
    settings_state = _patch_extra_roots(root, args.mount)

    owner = _resolve_owner(root)
    print(f"Conductor -> Odysseus Brain at {root}")
    print(f"  skills:   {n_roles} roles"
          f"{' + cdt driver' if driver_ok else ''}"
          f"{f' + {n_autos} automation(s)' if n_autos else ''}"
          f"  (owner={owner or 'none'}, status=published, category=conductor)")
    print(f"  docker:   docker-compose.override.yml {override_state} "
          f"({host} -> {args.mount})")
    print(f"  settings: tool_path_extra_roots {settings_state} ({args.mount})")
    print()
    print("Next: restart Odysseus so it picks up the mount + skills:")
    print(f"    cd {root} && docker compose up -d")
    print("Then open an agent-mode chat — the Conductor roles + /cdt appear in the "
          "skills index, and the agent can read/write files under "
          f"{args.mount}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
