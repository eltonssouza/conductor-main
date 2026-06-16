"""Best-effort project type + technology detection from root manifests.

Used by `conductor cdt init` to pick the role subset and seed the stack file;
the user's Claude finalizes the stack from the real manifests afterwards.

Monorepo-aware: scans the project root plus subdirectories up to two levels
deep (skipping vendored/build noise), so a fullstack repo with `backend/` and
`frontend/` manifests is detected even when the root holds only a thin shell
package.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

VALID_TYPES = ("backend", "frontend", "mobile", "fullstack", "library",
               "data", "unknown")

# Directories never worth scanning for manifests (vendored deps, build output,
# virtualenvs). Hidden dirs (.git, .cdt, .vercel, ...) are skipped separately.
SKIP_DIRS = frozenset({
    "node_modules", "dist", "build", "out", "target", "bin", "obj",
    "vendor", "coverage", "tmp", "temp", "__pycache__",
    "venv", ".venv", "env", "site-packages",
})
# How deep below the root to look for manifests (root=0).
MAX_DEPTH = 2


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _search_roots(root: Path) -> List[Path]:
    """Root plus its subdirectories up to MAX_DEPTH, skipping noise/hidden dirs."""
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


def detect(root: Path) -> Tuple[str, List[str], List[str]]:
    """Returns (type, technologies, evidence) from root + subdir manifests.

    Conservative: mixed front+back signals -> fullstack; nothing recognized ->
    unknown, so the command/owner can classify. Evidence entries are paths
    relative to the project root, so monorepo locations are visible.
    """
    search = _search_roots(root)
    techs: List[str] = []
    evidence: List[str] = []
    front = back = mobile = False

    def find(name: str) -> str | None:
        """First search root containing `name`; returns its relative path."""
        for r in search:
            p = r / name
            if p.exists():
                return _rel(p, root)
        return None

    def glob_first(pattern: str) -> str | None:
        for r in search:
            for m in r.glob(pattern):
                return _rel(m, root)
        return None

    # JS/TS ecosystem — merge deps from every package.json across the tree.
    deps: dict = {}
    pkg_paths: List[str] = []
    for r in search:
        p = r / "package.json"
        if p.exists():
            pkg = _read_json(p)
            if pkg:
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                pkg_paths.append(_rel(p, root))
    if pkg_paths:
        evidence.extend(pkg_paths)

    def has_dir(name: str) -> bool:
        return find(name) is not None

    if has_dir("angular.json") or "@angular/core" in deps:
        front = True; techs.append("Angular")
    if "react" in deps:
        if "react-native" in deps:
            mobile = True; techs.append("React Native")
        else:
            front = True; techs.append("React")
    if "vue" in deps:
        front = True; techs.append("Vue")
    if "svelte" in deps:
        front = True; techs.append("Svelte")
    if "next" in deps:
        front = True; techs.append("Next.js")
    if glob_first("vite.config.js") or glob_first("vite.config.ts"):
        front = True; techs.append("Vite")
    # Node backend. NestJS/Fastify are unambiguous. Express, however, also ships
    # as the SSR server of an Angular Universal app (@angular/ssr); in that case
    # it is not a separate backend, so only count it when no Angular SSR is present.
    if "@nestjs/core" in deps or "fastify" in deps:
        back = True; techs.append("Node.js")
    elif "express" in deps and not ("@angular/ssr" in deps or "@angular/core" in deps):
        back = True; techs.append("Node.js")

    # backend manifests
    for f, tech in (("pom.xml", "Java/Maven"), ("build.gradle", "Java/Gradle"),
                    ("go.mod", "Go"), ("Gemfile", "Ruby"),
                    ("composer.json", "PHP"), ("Cargo.toml", "Rust")):
        hit = find(f)
        if hit:
            back = True; techs.append(tech); evidence.append(hit)
    py = find("requirements.txt") or find("pyproject.toml") or find("manage.py")
    if py:
        back = True; techs.append("Python"); evidence.append(py)
    csproj = glob_first("*.csproj")
    if csproj:
        back = True; techs.append(".NET"); evidence.append(csproj)
    php = glob_first("*.php")  # composer.json is already handled above
    if php:
        back = True; techs.append("PHP"); evidence.append(php)

    # mobile manifests
    flutter = find("pubspec.yaml")
    if flutter:
        mobile = True; techs.append("Flutter"); evidence.append(flutter)
    if has_dir("android") and has_dir("ios"):
        mobile = True; evidence.append("android/+ios/")
    xcode = glob_first("*.xcodeproj")
    if xcode:
        mobile = True; techs.append("iOS/Xcode"); evidence.append(xcode)

    # Hand-written static site: HTML present but no package.json anywhere (so it
    # is not an unbuilt JS app). `index.html` is the strong signal; fall back to
    # any *.html at a search root. Guarded by `not deps` so real frontend
    # frameworks are never tagged "Static HTML".
    if not front and not deps:
        html = find("index.html") or glob_first("*.html")
        if html:
            front = True; techs.append("Static HTML"); evidence.append(html)

    if mobile:
        ptype = "mobile"
    elif front and back:
        ptype = "fullstack"
    elif front:
        ptype = "frontend"
    elif back:
        ptype = "backend"
    else:
        ptype = "unknown"

    return ptype, list(dict.fromkeys(techs)), list(dict.fromkeys(evidence))
