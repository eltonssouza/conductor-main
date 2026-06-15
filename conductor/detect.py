"""Best-effort project type + technology detection from root manifests.

Used by `conductor cdt init` to pick the role subset and seed the stack file;
the user's Claude finalizes the stack from the real manifests afterwards.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

VALID_TYPES = ("backend", "frontend", "mobile", "fullstack", "library",
               "data", "unknown")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def detect(root: Path) -> Tuple[str, List[str], List[str]]:
    """Returns (type, technologies, evidence) from root manifests.

    Conservative: mixed front+back signals -> fullstack; nothing recognized ->
    unknown, so the command/owner can classify.
    """
    techs: List[str] = []
    evidence: List[str] = []
    front = back = mobile = False

    def has(name: str) -> bool:
        return (root / name).exists()

    # JS/TS ecosystem
    pkg = _read_json(root / "package.json") if has("package.json") else {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if pkg:
        evidence.append("package.json")
    if has("angular.json") or "@angular/core" in deps:
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
    if any((root / f).exists() for f in ("vite.config.js", "vite.config.ts")):
        front = True; techs.append("Vite")
    if "express" in deps or "fastify" in deps or "@nestjs/core" in deps:
        back = True; techs.append("Node.js")

    # backend manifests
    for f, tech in (("pom.xml", "Java/Maven"), ("build.gradle", "Java/Gradle"),
                    ("go.mod", "Go"), ("Gemfile", "Ruby"),
                    ("composer.json", "PHP"), ("Cargo.toml", "Rust")):
        if has(f):
            back = True; techs.append(tech); evidence.append(f)
    if has("requirements.txt") or has("pyproject.toml"):
        back = True; techs.append("Python"); evidence.append("requirements/pyproject")
    if any(root.glob("*.csproj")):
        back = True; techs.append(".NET"); evidence.append("*.csproj")

    # mobile manifests
    if has("pubspec.yaml"):
        mobile = True; techs.append("Flutter"); evidence.append("pubspec.yaml")
    if has("android") and has("ios"):
        mobile = True; evidence.append("android/+ios/")
    if any(root.glob("*.xcodeproj")):
        mobile = True; techs.append("iOS/Xcode"); evidence.append("*.xcodeproj")

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

    return ptype, list(dict.fromkeys(techs)), evidence
