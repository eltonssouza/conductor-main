"""Tests for detect.library_stacks — project tech -> library `stack` ids."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from conductor.detect import library_stacks
from conductor.rag import stack as stack_mod


class TestLibraryStacks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _pkg(self, deps):
        (self.root / "package.json").write_text(
            json.dumps({"dependencies": deps}), encoding="utf-8")

    def _file(self, name, body=""):
        (self.root / name).write_text(body, encoding="utf-8")

    def test_empty_is_core_only(self):
        self.assertEqual(library_stacks(self.root), [])

    def test_java_maven(self):
        self._file("pom.xml", "<project/>")
        self.assertEqual(library_stacks(self.root), ["java"])

    def test_angular_adds_javascript(self):
        self._pkg({"@angular/core": "^21.0.0"})
        self.assertEqual(library_stacks(self.root), ["angular", "javascript"])

    def test_java_plus_angular(self):
        self._file("pom.xml", "<project/>")
        self._pkg({"@angular/core": "^21.0.0"})
        self.assertEqual(library_stacks(self.root), ["angular", "java", "javascript"])

    def test_go(self):
        self._file("go.mod", "module x")
        self.assertEqual(library_stacks(self.root), ["go"])

    def test_python(self):
        self._file("pyproject.toml", "[project]\nname='x'\n")
        self.assertEqual(library_stacks(self.root), ["python"])

    def test_react_native(self):
        self._pkg({"react": "18.0.0", "react-native": "0.74.0"})
        self.assertEqual(library_stacks(self.root), ["javascript", "react-native"])

    def test_ruby_rails(self):
        self._file("Gemfile", "source 'https://rubygems.org'\ngem 'rails', '~> 7'\n")
        self.assertEqual(library_stacks(self.root), ["rails", "ruby"])

    def test_graphql_dep(self):
        self._pkg({"@nestjs/core": "10.0.0", "graphql": "16.0.0"})
        self.assertIn("graphql", library_stacks(self.root))


class TestAutoSelect(unittest.TestCase):
    """`cdt up`'s auto_select_stacks: detect from cwd, accumulate, persist."""
    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._proj = tempfile.TemporaryDirectory()
        self.home = Path(self._home.name)
        self.proj = Path(self._proj.name)
        self.addCleanup(self._home.cleanup)
        self.addCleanup(self._proj.cleanup)
        self._cwd = os.getcwd()
        os.chdir(self.proj)
        self.addCleanup(lambda: os.chdir(self._cwd))
        self._patch = mock.patch.object(stack_mod, "REGISTRY_DIR", self.home)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_detects_and_persists(self):
        (self.proj / "go.mod").write_text("module x", encoding="utf-8")
        env = {}
        stack_mod.auto_select_stacks(env)
        self.assertEqual(env["CONDUCTOR_LIBRARY_STACKS"], "go")
        saved = json.loads((self.home / "library.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["stacks"], ["go"])

    def test_accumulates_across_projects(self):
        (self.home / "library.json").write_text('{"stacks": ["angular"]}', encoding="utf-8")
        (self.proj / "go.mod").write_text("module x", encoding="utf-8")
        env = {}
        stack_mod.auto_select_stacks(env)
        self.assertEqual(env["CONDUCTOR_LIBRARY_STACKS"], "angular,go")

    def test_explicit_override_is_untouched(self):
        (self.proj / "go.mod").write_text("module x", encoding="utf-8")
        env = {"CONDUCTOR_LIBRARY_STACKS": "ruby"}
        stack_mod.auto_select_stacks(env)
        self.assertEqual(env["CONDUCTOR_LIBRARY_STACKS"], "ruby")
        self.assertFalse((self.home / "library.json").exists())  # not persisted


if __name__ == "__main__":
    unittest.main()
