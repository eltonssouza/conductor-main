#!/usr/bin/env python3
"""`python -m rag.stack up` — launch the RAG stack, auto-detecting the GPU.

The plugin identifies an NVIDIA GPU and Docker's NVIDIA runtime; when both are
present it adds the GPU compose override so Ollama runs bge-m3 on the GPU
(~0.5 s/embed). Otherwise it tells you it is falling back to CPU (the full-corpus
ingest then takes hours). It also auto-locates the books archive.

  python -m rag.stack up            # attached (watch progress)
  python -m rag.stack up -d         # detached
  python -m rag.stack down          # stop the stack
  python -m rag.stack <any docker compose args...>
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parent.parent / "infra" / "conductor"
BASE = INFRA / "docker-compose.yml"
GPU = INFRA / "docker-compose.gpu.yml"
REPO_ROOT = Path(__file__).resolve().parent.parent


def has_nvidia_gpu() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True,
                              timeout=15).returncode == 0
    except Exception:
        return False


def docker_has_nvidia_runtime() -> bool:
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.Runtimes}}"],
                           capture_output=True, text=True, timeout=20)
        return "nvidia" in (r.stdout or "").lower()
    except Exception:
        return False


def resolve_archive(env: dict) -> None:
    """Auto-point CONDUCTOR_ARCHIVE at the repo-root to-brain.7z if not set."""
    if env.get("CONDUCTOR_ARCHIVE"):
        return
    local = INFRA / "to-brain.7z"
    root = REPO_ROOT / "to-brain.7z"
    if not local.exists() and root.exists():
        env["CONDUCTOR_ARCHIVE"] = "../../to-brain.7z"
        print(f"Books archive: {root} (CONDUCTOR_ARCHIVE=../../to-brain.7z)")
    elif local.exists():
        print(f"Books archive: {local}")
    else:
        print("WARNING: no to-brain.7z found (in infra/conductor/ or repo root). "
              "Set CONDUCTOR_ARCHIVE or the build will skip extraction.")


def select_compose_files() -> list:
    files = ["-f", str(BASE)]
    if has_nvidia_gpu():
        if docker_has_nvidia_runtime():
            files += ["-f", str(GPU)]
            print("GPU: NVIDIA GPU + Docker runtime detected — enabling GPU for "
                  "Ollama (~0.5s/embed).")
        else:
            print("GPU: NVIDIA GPU found, but Docker has no 'nvidia' runtime. "
                  "Install the NVIDIA Container Toolkit to use it.")
            print("     Falling back to CPU — full-corpus ingest takes hours.")
    else:
        print("GPU: none detected — CPU mode. Full-corpus ingest takes hours.")
    return files


def main(argv: list) -> int:
    if not shutil.which("docker"):
        print("ERROR: docker not found on PATH.", file=sys.stderr)
        return 2
    cmd = argv or ["up"]
    env = dict(os.environ)
    resolve_archive(env)
    files = select_compose_files()
    full = ["docker", "compose", *files, *cmd]
    print("+ " + " ".join(full))
    sys.stdout.flush()  # flush our notices before docker inherits stdout
    return subprocess.call(full, cwd=str(INFRA), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
