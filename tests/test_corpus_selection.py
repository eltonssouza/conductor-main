"""Tests for corpus selection — tier + language/framework `stack` filtering."""
import tempfile
import unittest
from pathlib import Path

from conductor.rag import core


def _book(dir_, name, fm, body="# Title\n\nSome prose about the topic.\n"):
    p = dir_ / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}", encoding="utf-8")
    return p


class TestIsSelected(unittest.TestCase):
    def test_agnostic_core_default(self):
        self.assertTrue(core.is_selected({"software_dev": "core"}, ["core"], []))

    def test_stack_excluded_by_default(self):
        self.assertFalse(core.is_selected({"software_dev": "core", "stack": "python"}, ["core"], []))

    def test_stack_included_when_chosen(self):
        self.assertTrue(core.is_selected({"software_dev": "core", "stack": "python"}, ["core"], ["python"]))

    def test_stack_all(self):
        self.assertTrue(core.is_selected({"software_dev": "core", "stack": "go"}, ["core"], ["all"]))

    def test_tier_excluded_by_default(self):
        self.assertFalse(core.is_selected({"software_dev": "supporting"}, ["core"], []))

    def test_missing_tier_defaults_core(self):
        self.assertTrue(core.is_selected({}, ["core"], []))

    def test_stack_tier_book_is_opt_in(self):
        # the corpus tags language/framework books `software_dev: stack` + `stack: <id>`
        meta = {"software_dev": "stack", "stack": "go"}
        self.assertFalse(core.is_selected(meta, ["core"], []))        # excluded by default
        self.assertTrue(core.is_selected(meta, ["core"], ["go"]))     # opt-in by stack


class TestIterCorpusSelection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lib = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _book(self.lib, "03_design/clean-arch.md", "software_dev: core")            # agnostic
        _book(self.lib, "01_languages/python.md", "software_dev: core\nstack: python")
        _book(self.lib, "06_web/angular.md", "software_dev: core\nstack: angular")
        _book(self.lib, "07_devops/sre.md", "software_dev: supporting")             # other tier

    def _sources(self, **kw):
        return {c.source for c in core.iter_corpus(self.lib, **kw)}

    def test_default_is_core_agnostic_only(self):
        self.assertEqual(self._sources(tiers=["core"], stacks=[]), {"clean-arch"})

    def test_opt_into_one_stack(self):
        self.assertEqual(self._sources(tiers=["core"], stacks=["angular"]),
                         {"clean-arch", "angular"})

    def test_all_stacks_and_tiers(self):
        got = self._sources(tiers=["core", "supporting"], stacks=["all"])
        self.assertEqual(got, {"clean-arch", "python", "angular", "sre"})

    def test_frontmatter_stripped_from_body(self):
        chunks = list(core.iter_corpus(self.lib, tiers=["core"], stacks=[]))
        joined = "\n".join(c.text for c in chunks)
        self.assertNotIn("software_dev", joined)


if __name__ == "__main__":
    unittest.main()
