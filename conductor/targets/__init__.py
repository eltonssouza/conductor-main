"""Harness target registry + resolution.

`cdt init --target claude|opencode|all` (default: auto-detect the harness already
used in the project, falling back to Claude Code). The resolved target keys are
persisted in `.cdt/config.json` so `cdt sync` re-emits for the same harness(es).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from .base import GuideContext, Target
from .claude import ClaudeTarget
from .codex import CodexTarget
from .opencode import OpenCodeTarget
from .pi import PiTarget

# Registration order is the precedence used when auto-detecting.
_REGISTRY = {t.key: t for t in
             (ClaudeTarget(), OpenCodeTarget(), CodexTarget(), PiTarget())}

DEFAULT_TARGET = "claude"


def available() -> List[str]:
    return list(_REGISTRY)


def get(key: str) -> Target:
    return _REGISTRY[key]


def resolve(spec: str | None, project: Path) -> List[Target]:
    """Turn a `--target` spec into the ordered list of targets to emit.

    - explicit `claude,opencode` (comma list) -> exactly those, validated
    - `all` -> every registered target
    - None -> auto-detect (every target whose harness is present); if none is
      detected, fall back to the default (Claude Code).
    """
    if spec and spec != "all":
        keys = [k.strip() for k in spec.split(",") if k.strip()]
        unknown = [k for k in keys if k not in _REGISTRY]
        if unknown:
            raise ValueError(f"unknown target(s): {', '.join(unknown)} "
                             f"(available: {', '.join(_REGISTRY)})")
        return [_REGISTRY[k] for k in keys]
    if spec == "all":
        return list(_REGISTRY.values())
    detected = [t for t in _REGISTRY.values() if t.detect(project)]
    return detected or [_REGISTRY[DEFAULT_TARGET]]
