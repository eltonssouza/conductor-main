"""Per-project paths, `.cdt/config.json`, and the global enrolled-projects registry.

Pure stdlib. A project is "enrolled" once it has a `.cdt/` directory; the global
registry (`~/.claude/conductor/projects.json`) answers "which projects use
Conductor" without scanning the disk.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

CDT_DIRNAME = ".cdt"
# Markers that identify a project root when walking up from the cwd.
ROOT_MARKERS = (".cdt", ".git", "package.json", "pyproject.toml", "go.mod",
                "pom.xml", "build.gradle", "Cargo.toml", "pubspec.yaml")

# Directories never worth scanning for manifests (vendored deps, build output,
# virtualenvs). Hidden dirs (.git, .cdt, .vercel, ...) are skipped separately.
SKIP_DIRS = frozenset({
    "node_modules", "dist", "build", "out", "target", "bin", "obj",
    "vendor", "coverage", "tmp", "temp", "__pycache__",
    "venv", ".venv", "env", "site-packages",
})
# How deep below a root to look for manifests (root=0).
MAX_DEPTH = 2

# Global registry of enrolled projects (outside any single project).
REGISTRY_DIR = Path(os.environ.get("CONDUCTOR_HOME",
                                   str(Path.home() / ".claude" / "conductor")))
REGISTRY_FILE = REGISTRY_DIR / "projects.json"

# Docker infra ships inside the package. The `conductor` image is built from a
# git build context (the public repo — see the compose `context:`), so neither
# the CLI nor the Docker stack needs a source clone on the host.
PACKAGE_INFRA = Path(__file__).resolve().parent / "infra"


def force_utf8() -> None:
    """Ensures stdout/stderr use UTF-8 (Windows console defaults to cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def debug_trace(context: str) -> None:
    """Print the current exception traceback to stderr when `CONDUCTOR_DEBUG` is set.

    Best-effort `except` blocks swallow errors so an optional backend being down
    never breaks the CLI — but that also hides real bugs. Call this inside such
    blocks so `CONDUCTOR_DEBUG=1` surfaces what was swallowed, with no change to
    the default (silent) behavior.
    """
    if not os.environ.get("CONDUCTOR_DEBUG"):
        return
    import traceback
    print(f"cdt: debug: swallowed error in {context}:", file=sys.stderr)
    traceback.print_exc()


def slugify(name: str) -> str:
    """kebab-case slug safe for a Honcho workspace id."""
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "project"


def find_project_root(start: Optional[Path] = None) -> Path:
    """Walks up from `start` (default cwd) to the first directory with a marker.

    Falls back to the starting directory if no marker is found.
    """
    start = (start or Path.cwd()).resolve()
    for d in (start, *start.parents):
        if any((d / m).exists() for m in ROOT_MARKERS):
            return d
    return start


def search_roots(root: Path) -> List[Path]:
    """Root plus its subdirectories up to MAX_DEPTH, skipping noise/hidden dirs.

    Monorepo-aware manifest search base: a fullstack repo with `backend/` and
    `frontend/` packages is discovered even when the root holds only a thin
    shell. Shared by detect.py so the walk-down lives in one place.
    """
    roots = [root]

    def walk(d: Path, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        try:
            children = sorted(d.iterdir())
        except OSError:
            return
        for child in children:
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in SKIP_DIRS:
                continue
            roots.append(child)
            walk(child, depth + 1)

    walk(root, 1)
    return roots


# --- per-project paths -------------------------------------------------------

def cdt_dir(root: Path) -> Path:
    return root / CDT_DIRNAME


def config_path(root: Path) -> Path:
    return cdt_dir(root) / "config.json"


def stack_dir(root: Path) -> Path:
    return cdt_dir(root) / "stack"


def memory_dir(root: Path) -> Path:
    """Root of the per-project memory tree (`.cdt/memory/`).

    Three natures live side by side: `diary/` (append-only machine events,
    source of truth), `docs/` + `records/` (living knowledge, committed), and
    `refs/` (pointers to external systems, never ingested by Honcho).
    """
    return cdt_dir(root) / "memory"


def diary_dir(root: Path) -> Path:
    """Append-only JSONL mirror, one file per day. Source of truth, local-only."""
    return memory_dir(root) / "diary"


def daily_dir(root: Path) -> Path:
    """Human-readable digests generated from the diary. Local-only."""
    return memory_dir(root) / "daily"


def docs_dir(root: Path) -> Path:
    """Living architecture/api/db/ops snapshots (committed knowledge)."""
    return memory_dir(root) / "docs"


def records_dir(root: Path) -> Path:
    """Dated/numbered artefacts: bugs, ADRs, discovery, features, gaps."""
    return memory_dir(root) / "records"


def refs_dir(root: Path) -> Path:
    """Pointers to external systems (Jira, PRDs, SQL, images). Not memory."""
    return memory_dir(root) / "refs"


def journal_dir(root: Path) -> Path:
    """Back-compat alias: the diary now lives under `memory/diary/`."""
    return diary_dir(root)


def is_enrolled(root: Path) -> bool:
    return config_path(root).is_file()


def read_config(root: Path) -> Optional[dict]:
    p = config_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` atomically (temp file in the same dir + os.replace).

    A crash mid-write can no longer truncate or corrupt the JSON state files —
    the reader sees either the old file or the fully-written new one, never a
    half-written one. Same-directory temp keeps `os.replace` on one filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_config(root: Path, config: dict) -> None:
    _atomic_write(config_path(root),
                  json.dumps(config, indent=2, ensure_ascii=False) + "\n")


# --- global registry ---------------------------------------------------------

def _load_registry() -> dict:
    if not REGISTRY_FILE.is_file():
        return {"projects": []}
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        data.setdefault("projects", [])
        return data
    except (ValueError, OSError) as e:
        print(f"cdt: warning: project registry unreadable at {REGISTRY_FILE} "
              f"({e}); starting from empty", file=sys.stderr)
        return {"projects": []}


def register_project(root: Path, slug: str, ptype: str) -> None:
    """Adds/updates the project in the global registry (keyed by absolute path)."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    data = _load_registry()
    path = str(root.resolve())
    entry = {"path": path, "slug": slug, "type": ptype}
    others = [p for p in data["projects"] if p.get("path") != path]
    data["projects"] = sorted([*others, entry], key=lambda p: p["path"])
    _atomic_write(REGISTRY_FILE,
                  json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def list_projects() -> List[dict]:
    return _load_registry()["projects"]
