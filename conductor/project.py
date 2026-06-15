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
from pathlib import Path
from typing import List, Optional

CDT_DIRNAME = ".cdt"
# Markers that identify a project root when walking up from the cwd.
ROOT_MARKERS = (".cdt", ".git", "package.json", "pyproject.toml", "go.mod",
                "pom.xml", "build.gradle", "Cargo.toml", "pubspec.yaml")

# Global registry of enrolled projects (outside any single project).
REGISTRY_DIR = Path(os.environ.get("CONDUCTOR_HOME",
                                   str(Path.home() / ".claude" / "conductor")))
REGISTRY_FILE = REGISTRY_DIR / "projects.json"

# Docker infra ships inside the package. The `conductor` image is built from the
# local source, so the Docker stack runs from a repo clone (the CLI does not).
PACKAGE_INFRA = Path(__file__).resolve().parent / "infra"


def force_utf8() -> None:
    """Ensures stdout/stderr use UTF-8 (Windows console defaults to cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


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


# --- per-project paths -------------------------------------------------------

def cdt_dir(root: Path) -> Path:
    return root / CDT_DIRNAME


def config_path(root: Path) -> Path:
    return cdt_dir(root) / "config.json"


def stack_dir(root: Path) -> Path:
    return cdt_dir(root) / "stack"


def journal_dir(root: Path) -> Path:
    return cdt_dir(root) / "journal"


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


def write_config(root: Path, config: dict) -> None:
    cdt_dir(root).mkdir(parents=True, exist_ok=True)
    config_path(root).write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- global registry ---------------------------------------------------------

def _load_registry() -> dict:
    if not REGISTRY_FILE.is_file():
        return {"projects": []}
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        data.setdefault("projects", [])
        return data
    except (ValueError, OSError):
        return {"projects": []}


def register_project(root: Path, slug: str, ptype: str) -> None:
    """Adds/updates the project in the global registry (keyed by absolute path)."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    data = _load_registry()
    path = str(root.resolve())
    entry = {"path": path, "slug": slug, "type": ptype}
    others = [p for p in data["projects"] if p.get("path") != path]
    data["projects"] = sorted([*others, entry], key=lambda p: p["path"])
    REGISTRY_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def list_projects() -> List[dict]:
    return _load_registry()["projects"]
