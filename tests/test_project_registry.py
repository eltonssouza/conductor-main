"""Unit tests for project.py: atomic writes, the global registry, and debug_trace.

Pure stdlib (`unittest`), no Docker/network/extras. The registry globals are
redirected to a temp dir per test so the user's real `~/.claude/conductor`
registry is never touched.

Run: `python -m unittest discover -s tests` (or `python tools/test.py`).
"""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from conductor import project


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_writes_content_and_creates_parents(self):
        p = self.dir / "sub" / "f.json"
        project._atomic_write(p, '{"a": 1}\n')
        self.assertEqual(p.read_text(encoding="utf-8"), '{"a": 1}\n')

    def test_leaves_no_temp_file_behind(self):
        p = self.dir / "f.json"
        project._atomic_write(p, "x\n")
        leftover = [x.name for x in self.dir.iterdir() if x.name != "f.json"]
        self.assertEqual(leftover, [])

    def test_overwrite_replaces_atomically(self):
        p = self.dir / "f.json"
        project._atomic_write(p, "old\n")
        project._atomic_write(p, "new\n")
        self.assertEqual(p.read_text(encoding="utf-8"), "new\n")


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self._orig = (project.REGISTRY_DIR, project.REGISTRY_FILE)
        project.REGISTRY_DIR = self.base / "reg"
        project.REGISTRY_FILE = project.REGISTRY_DIR / "projects.json"
        self.addCleanup(self._restore)

    def _restore(self):
        project.REGISTRY_DIR, project.REGISTRY_FILE = self._orig

    def test_register_is_sorted_by_path_and_dedups(self):
        a, b = self.base / "a-proj", self.base / "b-proj"
        a.mkdir()
        b.mkdir()
        project.register_project(b, "b", "backend")
        project.register_project(a, "a", "frontend")
        project.register_project(a, "a2", "frontend")  # update, not a duplicate
        items = project.list_projects()
        self.assertEqual(len(items), 2)
        self.assertEqual([i["slug"] for i in items], ["a2", "b"])

    def test_empty_registry_returns_empty(self):
        self.assertEqual(project.list_projects(), [])

    def test_corrupt_registry_warns_and_recovers(self):
        project.REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        project.REGISTRY_FILE.write_text("{not json", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stderr(buf):
            items = project.list_projects()
        self.assertEqual(items, [])
        self.assertIn("registry unreadable", buf.getvalue())


class TestDebugTrace(unittest.TestCase):
    def setUp(self):
        self._had = os.environ.pop("CONDUCTOR_DEBUG", None)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._had is None:
            os.environ.pop("CONDUCTOR_DEBUG", None)
        else:
            os.environ["CONDUCTOR_DEBUG"] = self._had

    def test_silent_by_default(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            try:
                raise ValueError("x")
            except Exception:
                project.debug_trace("ctx")
        self.assertEqual(buf.getvalue(), "")

    def test_prints_when_enabled(self):
        os.environ["CONDUCTOR_DEBUG"] = "1"
        buf = io.StringIO()
        with redirect_stderr(buf):
            try:
                raise ValueError("boom")
            except Exception:
                project.debug_trace("ctx")
        out = buf.getvalue()
        self.assertIn("ctx", out)
        self.assertIn("boom", out)


if __name__ == "__main__":
    unittest.main()
