#!/usr/bin/env python3
"""`cdt update` — upgrade Conductor to the latest published source.

The installer puts Conductor on the machine as a real package straight from the
public repo (`uv tool install` / `pipx install` of `conductor @ git+…`), with no
source clone. So the update is a package upgrade:

  cdt update              # uv tool upgrade / pipx upgrade (re-pulls the git ref)

Contributor convenience: if the package is imported from an editable *git clone*
(a `.git` sits next to it — e.g. `pip install -e .`), `cdt update` does a
`git pull --ff-only` on that clone instead, so live edits keep working.

  cdt update --reinstall  # after a pull, reinstall deps if pyproject changed
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Package lives at <root>/conductor/; a dev clone has pyproject + .git one up.
REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/eltonssouza/conductor-main.git"


def _current_branch() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return "?"


def _run(cmd: list, timeout: int = 600, cwd: str | None = None) -> int:
    print("+ " + " ".join(cmd))
    try:
        return subprocess.run(cmd, timeout=timeout, cwd=cwd).returncode
    except subprocess.TimeoutExpired:
        print(f"'{cmd[0]}' timed out after {timeout}s — network or remote "
              "unreachable. Re-run when connectivity is restored.", file=sys.stderr)
        return 1


def _installed_via_uv() -> bool:
    """True if `conductor` is a uv-managed tool (so `uv tool upgrade` applies)."""
    if not shutil.which("uv"):
        return False
    try:
        r = subprocess.run(["uv", "tool", "list"], capture_output=True,
                           text=True, timeout=20)
        return any(line.split()[:1] == ["conductor"]
                   for line in (r.stdout or "").splitlines())
    except Exception:
        return False


def _package_upgrade() -> int:
    """Upgrade the installed package via its manager (no clone present)."""
    if _installed_via_uv():
        return _run(["uv", "tool", "upgrade", "conductor"])
    if shutil.which("pipx"):
        return _run(["pipx", "upgrade", "conductor"])
    # Neither manager found — tell the user how to upgrade by hand.
    print("Installed as a package, but neither uv nor pipx is on PATH.")
    print("Upgrade with one of:")
    print("  uv tool upgrade conductor")
    print("  pipx upgrade conductor")
    print(f'  pip install --upgrade --force-reinstall "conductor @ git+{REPO_URL}@main"')
    return 1


def main(argv: list) -> int:
    reinstall = "--reinstall" in (argv or [])

    # --- editable/dev clone: keep the fast git-pull path for contributors ----
    if (REPO_ROOT / ".git").exists():
        if not shutil.which("git"):
            print("ERROR: git not found on PATH.", file=sys.stderr)
            return 2
        branch = _current_branch()
        print(f"Updating {REPO_ROOT} (branch: {branch}) ...")
        rc = _run(["git", "pull", "--ff-only"], timeout=300, cwd=str(REPO_ROOT))
        if rc != 0:
            print("git pull failed — local changes or a diverged branch. "
                  "Resolve manually, then re-run.", file=sys.stderr)
            return rc
        if reinstall:
            print("Reinstalling dependencies ...")
            pip = [sys.executable, "-m", "pip", "install", "-q", "-e", ".[rag,honcho]"]
            try:
                result = subprocess.run(pip, cwd=str(REPO_ROOT), timeout=600,
                                        capture_output=True, text=True)
                if result.returncode != 0:
                    sys.stderr.write(result.stderr)
                    return result.returncode
            except subprocess.TimeoutExpired:
                print("pip install timed out after 600s.", file=sys.stderr)
                return 1
        else:
            print("Code is live (editable install). If pyproject deps changed, "
                  "run `cdt update --reinstall`.")
        print("Done.")
        return 0

    # --- normal case: installed package, no clone → manager upgrade ----------
    rc = _package_upgrade()
    if rc == 0:
        print("Done. Conductor upgraded to the latest published source.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
