#!/usr/bin/env python3
"""`python tools/test.py` — the project's test runner (pure stdlib).

Runs the template invariant validator (R1–R8) and then the functional
`unittest` suite under `tests/`. No third-party deps, no Docker, no network — so
it runs anywhere `python` does, including CI without an install step.

Exit code is non-zero if either stage fails.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Make `import conductor` / `tests.*` work without an install (CI runs clean).
sys.path.insert(0, str(ROOT))


def _run_validator() -> bool:
    print("== validate (R1-R11) ==", flush=True)
    rc = subprocess.call([sys.executable, str(ROOT / "tools" / "validate.py")])
    return rc == 0


def _run_unittests() -> bool:
    print("\n== unittest (tests/) ==", flush=True)
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def main() -> int:
    ok_validate = _run_validator()
    ok_tests = _run_unittests()
    print("\n" + ("ALL GREEN" if (ok_validate and ok_tests) else "FAILURES — see above"))
    return 0 if (ok_validate and ok_tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
