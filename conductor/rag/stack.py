#!/usr/bin/env python3
"""`cdt up|down` — launch the RAG stack, auto-detecting the GPU.

Conductor identifies an NVIDIA GPU and Docker's NVIDIA runtime; when both are
present it adds the GPU compose override so Ollama runs bge-m3 on the GPU
(~0.5 s/embed). Otherwise it falls back to CPU (full-corpus ingest takes hours).
It also auto-locates the books archive (cwd or CONDUCTOR_ARCHIVE).

The Docker infra ships inside the package; the `conductor` image is built from
the local source, so the Docker stack needs a repo clone (the CLI itself does not).

  cdt up            # attached (watch progress)
  cdt up -d         # detached
  cdt down          # stop the stack
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..project import PACKAGE_INFRA


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
    """Sets CONDUCTOR_ARCHIVE to an ABSOLUTE path (compose runs from the staged
    infra dir, so a relative path would resolve wrong)."""
    val = env.get("CONDUCTOR_ARCHIVE")
    if val:
        p = Path(val)
        env["CONDUCTOR_ARCHIVE"] = str(p if p.is_absolute() else (Path.cwd() / p).resolve())
        print(f"Books archive: {env['CONDUCTOR_ARCHIVE']}")
        return
    cand = Path.cwd() / "to-brain.7z"
    if cand.is_file():
        env["CONDUCTOR_ARCHIVE"] = str(cand.resolve())
        print(f"Books archive: {cand.resolve()}")
    else:
        print("WARNING: no to-brain.7z in the cwd. Set CONDUCTOR_ARCHIVE to your "
              "archive, or the build will skip extraction (empty index).")


def select_compose_files(infra: Path) -> list:
    files = ["-f", str(infra / "docker-compose.yml")]
    if has_nvidia_gpu():
        if docker_has_nvidia_runtime():
            files += ["-f", str(infra / "docker-compose.gpu.yml")]
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
    infra = PACKAGE_INFRA / "conductor"
    if not (infra / "docker-compose.yml").is_file():
        print(f"ERROR: docker infra not found at {infra}. The Docker stack needs "
              "a repo clone (build from source).", file=sys.stderr)
        return 2
    cmd = argv or ["up"]
    env = dict(os.environ)
    resolve_archive(env)
    files = select_compose_files(infra)
    full = ["docker", "compose", *files, *cmd]
    print("+ " + " ".join(full))
    sys.stdout.flush()  # flush our notices before docker inherits stdout
    return subprocess.call(full, cwd=str(infra), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
