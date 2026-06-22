#!/usr/bin/env python3
"""`cdt up|down` — launch the RAG stack, auto-detecting the GPU.

Conductor identifies an NVIDIA GPU and Docker's NVIDIA runtime; when both are
present it adds the GPU compose override so Ollama runs bge-m3 on the GPU
(~0.5 s/embed). Otherwise it falls back to CPU (full-corpus ingest takes hours).
The book corpus is fetched from the public library repo by the `conductor`
service (CONDUCTOR_LIBRARY_REPO@REF); no local archive is required.

The Docker infra ships inside the package; the `conductor` image is built from
the local source, so the Docker stack needs a repo clone (the CLI itself does not).

  cdt up            # attached (watch progress)
  cdt up -d         # detached
  cdt down          # stop the stack
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..project import PACKAGE_INFRA, REGISTRY_DIR


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


def auto_select_stacks(env: dict) -> None:
    """Auto-pick the library stacks from the current project's detected tech,
    unless the user set `CONDUCTOR_LIBRARY_STACKS` explicitly.

    The library is a single global index, so the choice **accumulates**: each
    `cdt up` run unions the project's detected stacks with the set picked on
    earlier runs (persisted under CONDUCTOR_HOME). Switching from an Angular
    project to a Ruby one grows the index to cover both instead of dropping one.
    """
    if env.get("CONDUCTOR_LIBRARY_STACKS"):
        return  # explicit override wins; don't auto-detect or persist
    from ..detect import library_stacks
    from ..project import find_project_root
    detected = set(library_stacks(find_project_root()))
    store = REGISTRY_DIR / "library.json"
    prev: set = set()
    if store.is_file():
        try:
            prev = set(json.loads(store.read_text(encoding="utf-8")).get("stacks", []))
        except (ValueError, OSError):
            prev = set()
    union = sorted(prev | detected)
    if not union:
        print("Library: no project stacks detected — ingesting core (language-agnostic).")
        return
    env["CONDUCTOR_LIBRARY_STACKS"] = ",".join(union)
    try:
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps({"stacks": union}, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    new = sorted(detected - prev)
    note = f"detected {', '.join(sorted(detected))}" if detected else "no new stacks here"
    grew = f" (+{', '.join(new)})" if new else ""
    print(f"Library stacks: {', '.join(union)}{grew}  [{note}]")


def resolve_library_source(env: dict) -> None:
    """Report where the book corpus comes from.

    By default the `conductor` service fetches it from the public library repo
    (CONDUCTOR_LIBRARY_REPO@REF) — nothing local is required. An offline seed is
    still possible by setting CONDUCTOR_LIBRARY_ARCHIVE to a mounted .7z."""
    archive = env.get("CONDUCTOR_LIBRARY_ARCHIVE")
    if archive:
        print(f"Library source: offline archive {archive}")
        return
    repo = env.get("CONDUCTOR_LIBRARY_REPO", "eltonssouza/conductor-library")
    ref = env.get("CONDUCTOR_LIBRARY_REF", "main")
    print(f"Library source: github.com/{repo}@{ref} (fetched into the stack)")


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
    if cmd[0] not in ("down", "stop"):     # only when bringing the stack up
        auto_select_stacks(env)
    resolve_library_source(env)
    files = select_compose_files(infra)
    full = ["docker", "compose", *files, *cmd]
    print("+ " + " ".join(full))
    sys.stdout.flush()  # flush our notices before docker inherits stdout
    return subprocess.call(full, cwd=str(infra), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
