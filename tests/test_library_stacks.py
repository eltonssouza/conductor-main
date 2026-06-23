"""Tests for stack discovery + the interactive `cdt library stacks` chooser."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from conductor import library
from conductor.rag import core


def _index_blob(stacks):
    """Build a LIBRARY_INDEX.json byte blob from {sid: {"versions", "category"}}."""
    manifest = {"schema": "conductor-library-index/v1", "stacks": {}}
    for sid, info in stacks.items():
        vers = info["versions"]
        cat = info["category"]
        editions = ([{"path": f"{cat}/{sid}-{v}.md", "title": f"{sid} {v}", "version": v}
                     for v in vers]
                    or [{"path": f"{cat}/{sid}.md", "title": sid}])
        manifest["stacks"][sid] = {"versions": vers, "editions": editions}
    return json.dumps(manifest).encode("utf-8")


class _Resp:
    def __init__(self, b): self.b = b
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False


class TestDiscoverStacks(unittest.TestCase):
    def test_groups_versions_and_category(self):
        blob = _index_blob({
            "angular": {"versions": [21, 22], "category": "14_frameworks"},
            "go": {"versions": [], "category": "01_programming_languages"},
        })
        with mock.patch("urllib.request.urlopen", return_value=_Resp(blob)):
            out = core.discover_stacks("x/y", "main")
        self.assertEqual(set(out), {"angular", "go"})
        self.assertEqual(out["angular"]["versions"], ["21", "22"])
        self.assertEqual(out["angular"]["category"], "14_frameworks")
        self.assertEqual(out["go"]["versions"], [])

    def test_unreachable_returns_empty(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("no net")):
            self.assertEqual(core.discover_stacks("x/y", "main"), {})


class TestChooser(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lib = Path(self._tmp.name) / "library.json"
        self._p = mock.patch.object(library, "_library_json", return_value=self.lib)
        self._p.start(); self.addCleanup(self._p.stop)
        self._avail = {
            "java": {"versions": [], "category": "01_programming_languages"},
            "angular": {"versions": ["21", "22"], "category": "14_frameworks"},
            "go": {"versions": [], "category": "01_programming_languages"},
        }

    def _choose(self, stacks_ans, tiers_ans=""):
        # two input() prompts: stacks, then tiers
        with mock.patch("conductor.rag.core.discover_stacks", return_value=self._avail), \
             mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("builtins.input", side_effect=[stacks_ans, tiers_ans]):
            return library.cmd_stacks([])

    def test_choose_by_id_and_pin_version_persists(self):
        rc = self._choose("java, angular@21")
        self.assertEqual(rc, 0)
        saved = json.loads(self.lib.read_text(encoding="utf-8"))
        self.assertEqual(saved["stacks"], ["angular@21", "java"])
        self.assertEqual(saved["tiers"], ["core"])           # blank tiers -> core

    def test_all(self):
        self._choose("all")
        self.assertEqual(json.loads(self.lib.read_text())["stacks"], ["angular", "go", "java"])

    def test_blank_keeps_current(self):
        self.lib.write_text('{"stacks": ["go"], "tiers": ["core"]}', encoding="utf-8")
        self._choose("")
        self.assertEqual(json.loads(self.lib.read_text())["stacks"], ["go"])  # unchanged

    def test_tiers_selection(self):
        self._choose("java", "supporting, foundational, bogus")
        saved = json.loads(self.lib.read_text(encoding="utf-8"))
        self.assertEqual(saved["stacks"], ["java"])
        self.assertEqual(saved["tiers"], ["core", "foundational", "supporting"])  # core always, bogus dropped


if __name__ == "__main__":
    unittest.main()
