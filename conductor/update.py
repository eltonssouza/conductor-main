#!/usr/bin/env python3
"""`conductor update` — pull the latest source of an editable/source install.

An editable install (`pip install -e`) imports the package straight from the
git clone, so `git pull` in that clone updates the CLI live — no reinstall
needed unless the dependencies in pyproject.toml changed (then `--reinstall`).

A non-editable install (pip/pipx from a built artifact) has no clone to pull;
this prints the right upgrade command instead.

  conductor update              # git pull the current branch (ff-only)
  conductor update --reinstall  # then pip install -e ".[rag,honcho]"
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Package lives at <repo>/conductor/; the repo root (pyproject + .git) is its parent.
REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/eltonssouza/conductor-main.git"


def _current_branch() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return "?"


def main(argv: list) -> int:
    reinstall = "--reinstall" in (argv or [])

    if not (REPO_ROOT / ".git").exists():
        print("Not a git source clone — this looks like a pip/pipx install.")
        print("Update with one of:")
        print("  pipx upgrade conductor")
        print(f'  pip install --upgrade --force-reinstall "git+{REPO_URL}"')
        return 0

    if not shutil.which("git"):
        print("ERROR: git not found on PATH.", file=sys.stderr)
        return 2

    branch = _current_branch()
    print(f"Updating {REPO_ROOT} (branch: {branch}) ...")
    rc = subprocess.call(["git", "pull", "--ff-only"], cwd=str(REPO_ROOT))
    if rc != 0:
        print("git pull failed — local changes or a diverged branch. "
              "Resolve manually, then re-run.", file=sys.stderr)
        return rc

    if reinstall:
        pip = [sys.executable, "-m", "pip", "install", "-e", ".[rag,honcho]"]
        print("+ " + " ".join(pip))
        rc = subprocess.call(pip, cwd=str(REPO_ROOT))
        if rc != 0:
            return rc
    else:
        print("Code is live (editable install). If pyproject deps changed, run "
              "`conductor update --reinstall`.")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
