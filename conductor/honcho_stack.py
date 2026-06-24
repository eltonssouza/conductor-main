#!/usr/bin/env python3
"""`cdt honcho up|down` — run the self-hosted Honcho diary backend.

Codifies the steps the Honcho stack needs (the git-URL build context fails on
Docker Desktop/Windows, Windows clones give the shell scripts CRLF endings, and
a fresh DB needs its vector dimension reconfigured for local bge-m3 embeddings):

  up   — clone Honcho if missing, fix CRLF, `docker compose up -d --build`
         (HONCHO_SRC = the clone); on a dimension mismatch, run Honcho's
         configure_embeddings once and bring it up again.
  down — stop the stack.

Run `cdt honcho-setup` first to write the .env, and `cdt up` so the
local bge-m3 (used for Honcho's embeddings) is reachable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .project import PACKAGE_INFRA, REGISTRY_DIR

HONCHO_REPO = "https://github.com/plastic-labs/honcho.git"
INFRA = PACKAGE_INFRA / "honcho"


def _honcho_src() -> Path:
    env = os.environ.get("HONCHO_SRC")
    return Path(env) if env else (REGISTRY_DIR / "honcho-src")


def _ensure_clone(src: Path) -> bool:
    if not (src / ".git").is_dir():
        print(f"cloning Honcho -> {src}")
        try:
            # Shallow clone over the network; 300s bounds a hung fetch.
            rc = subprocess.run(
                ["git", "clone", "--depth", "1", HONCHO_REPO, str(src)],
                timeout=300).returncode
        except subprocess.TimeoutExpired:
            print("ERROR: git clone timed out after 300s — network or remote "
                  "unreachable.", file=sys.stderr)
            return False
        if rc != 0:
            print("ERROR: git clone failed", file=sys.stderr)
            return False
    # Windows clones give the entrypoint CRLF endings -> `set: Illegal option`.
    for sh in src.rglob("*.sh"):
        try:
            data = sh.read_bytes()
            if b"\r\n" in data:
                sh.write_bytes(data.replace(b"\r\n", b"\n"))
        except OSError:
            pass
    return True


def _compose(src: Path, *args: str) -> int:
    env = {**os.environ, "HONCHO_SRC": str(src)}
    # All callers use detached/`down` forms (never foreground `up`), so the
    # command should return promptly. `up -d --build` can still pull and build
    # images, so 1800s (30min) is generous headroom while still bounding a true
    # hang (e.g. a stuck pull) instead of blocking forever.
    try:
        return subprocess.run(
            ["docker", "compose", "-f", str(INFRA / "docker-compose.yml"), *args],
            cwd=str(INFRA), env=env, timeout=1800).returncode
    except subprocess.TimeoutExpired:
        print(f"ERROR: `docker compose {' '.join(args)}` timed out after 1800s.",
              file=sys.stderr)
        return 1


def _api_health() -> str:
    try:
        r = subprocess.run(["docker", "inspect", "honcho-api-1",
                            "--format", "{{.State.Health.Status}}"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def _wait_health(timeout: int = 180) -> str:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        h = _api_health()
        if h in ("healthy", "unhealthy"):
            return h
        time.sleep(3)
    return _api_health() or "unknown"


def _dim_mismatch() -> bool:
    try:
        r = subprocess.run(["docker", "logs", "honcho-api-1"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
        log = r.stdout + r.stderr
        return "EMBEDDING_VECTOR_DIMENSIONS" in log and "does not match" in log
    except Exception:
        return False


def _configure_embeddings(src: Path) -> int:
    print("dimension mismatch — running configure_embeddings (one-time)...")
    env = {**os.environ, "HONCHO_SRC": str(src),
           "MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*"}
    # One-shot reconfigure script; 600s is ample and bounds a hang.
    try:
        return subprocess.run(
            ["docker", "compose", "-f", str(INFRA / "docker-compose.yml"),
             "run", "--rm", "--no-deps", "--entrypoint", "/app/.venv/bin/python",
             "deriver", "scripts/configure_embeddings.py", "--yes"],
            cwd=str(INFRA), env=env, timeout=600).returncode
    except subprocess.TimeoutExpired:
        print("ERROR: configure_embeddings timed out after 600s.", file=sys.stderr)
        return 1


def main(argv: list) -> int:
    if not shutil.which("docker"):
        print("ERROR: docker not found on PATH.", file=sys.stderr)
        return 2
    cmd = argv[0] if argv else "up"
    src = _honcho_src()

    if cmd == "down":
        return _compose(src, "down")
    if cmd != "up":
        print("usage: cdt honcho up|down", file=sys.stderr)
        return 2

    if not (INFRA / ".env").is_file():
        print("No .env yet — run `cdt honcho-setup` first.", file=sys.stderr)
        return 2
    if not _ensure_clone(src):
        return 1

    print("starting Honcho (building from the local clone)...")
    _compose(src, "up", "-d", "--build")
    health = _wait_health()
    if health != "healthy" and _dim_mismatch():
        _configure_embeddings(src)
        _compose(src, "up", "-d")
        health = _wait_health()

    print(f"Honcho api: {health}")
    if health == "healthy":
        print("Honcho ready — `cdt journal recall` now uses dialectic.")
        print("(Ensure `cdt up` is running: Honcho embeds via the local bge-m3.)")
        return 0
    print("Honcho not healthy — inspect `docker logs honcho-api-1`.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
