"""Unit tests for scaffold.py helpers (rendering + per-target emission).

Pure stdlib (`unittest`), no Docker/network/extras: exercises the small,
pure-ish helpers that the E2E init/sync test only covers end-to-end, so a
regression in stack rendering or target fan-out is caught in isolation.

Run: `python -m unittest discover -s tests` (or `python tools/test.py`).
"""
import tempfile
import unittest
from pathlib import Path

from conductor import scaffold
from conductor.project import stack_dir


class TestStackMd(unittest.TestCase):
    def test_renders_type_profile_and_meta(self):
        md = scaffold._stack_md(
            "backend", ["python"], ["pyproject.toml"],
            {"languages": ["Python 3.11"], "frameworks": ["FastAPI"]})
        self.assertIn("# Stack — backend", md)
        self.assertIn("Python 3.11", md)
        self.assertIn("FastAPI", md)
        self.assertIn("<!-- detected tags: python -->", md)
        self.assertIn("<!-- detection evidence: pyproject.toml -->", md)

    def test_empty_profile_marks_not_detected(self):
        md = scaffold._stack_md("library", [], [], None)
        self.assertIn("# Stack — library", md)
        self.assertIn("_(not detected", md)
        self.assertIn("<!-- detected tags: none -->", md)
        self.assertIn("<!-- detection evidence: none -->", md)


class TestWriteStackFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_writes_named_file(self):
        scaffold._write_stack_file(self.root, "backend", ["go"], ["go.mod"], None)
        out = stack_dir(self.root) / "backend.md"
        self.assertTrue(out.is_file())
        self.assertIn("# Stack — backend", out.read_text(encoding="utf-8"))


class _FakeTarget:
    """Minimal Target stand-in counting emit calls."""

    def __init__(self, label="Fake"):
        self.label = label
        self.calls = {"roles": 0, "driver": 0, "hooks": 0}

    def emit_roles(self, root, selected):
        self.calls["roles"] += 1
        return len(selected)

    def emit_driver(self, root):
        self.calls["driver"] += 1
        return True

    def emit_hooks(self, root):
        self.calls["hooks"] += 1
        return 2


class TestEmitTargets(unittest.TestCase):
    def test_emits_each_target_and_returns_role_count(self):
        t1, t2 = _FakeTarget("A"), _FakeTarget("B")
        n = scaffold._emit_targets(Path("."), [t1, t2], ["a", "b", "c"])
        self.assertEqual(n, 3)
        for t in (t1, t2):
            self.assertEqual(t.calls, {"roles": 1, "driver": 1, "hooks": 1})


if __name__ == "__main__":
    unittest.main()
