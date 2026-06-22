"""Functional tests for the harness target layer + guide rendering.

Pure stdlib (`unittest`), no Docker/network/extras: every target is exercised by
emitting into a temp dir and asserting the native layout, the translated
frontmatter, and the idempotency of the managed-region splice.

Run: `python -m unittest discover -s tests` (or `python tools/test.py`).
"""
import tempfile
import unittest
from pathlib import Path

from conductor import roles as roles_mod
from conductor import targets as targets_mod
from conductor.targets import base
from conductor.targets.base import GuideContext, TEMPLATES

SOME_ROLES = ["software-engineer", "software-architect", "frontend-engineer"]


class TempProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def ctx(self, ptype="backend"):
        return GuideContext(self.root, "proj", ptype, SOME_ROLES)


class TestFrontmatter(unittest.TestCase):
    def test_split_keeps_quoted_description(self):
        md = '---\nname: x\ndescription: "Has: a colon, and \\"quotes\\"."\n---\n\nBody.\n'
        meta, body = base.split_frontmatter(md)
        self.assertEqual(meta["name"], "x")
        self.assertEqual(meta["description"], '"Has: a colon, and \\"quotes\\"."')
        self.assertEqual(body.strip(), "Body.")

    def test_split_no_frontmatter_is_identity(self):
        meta, body = base.split_frontmatter("no frontmatter here")
        self.assertEqual(meta, {})
        self.assertEqual(body, "no frontmatter here")

    def test_join_roundtrip(self):
        meta = {"name": "x", "mode": "subagent"}
        out = base.join_frontmatter(meta, "Body.")
        meta2, body2 = base.split_frontmatter(out)
        self.assertEqual(meta2, meta)
        self.assertEqual(body2.strip(), "Body.")


class TestMergeRoleSkill(unittest.TestCase):
    def test_folds_persona_tier_and_steps(self):
        merged = base.merge_role_skill("software-engineer")
        self.assertIsNotNone(merged)
        slug, desc, body = merged
        self.assertEqual(slug, roles_mod.ROLES["software-engineer"].skill)
        self.assertIn("Model tier", body)              # tier hint injected
        self.assertIn("Software Engineer", body)        # agent persona present
        self.assertIn("When to use", body)              # skill steps present
        self.assertTrue(desc.startswith('"'))           # quoted skill description


class TestResolve(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_explicit_list(self):
        keys = [t.key for t in targets_mod.resolve("opencode,codex", self.root)]
        self.assertEqual(keys, ["opencode", "codex"])

    def test_all(self):
        self.assertEqual(len(targets_mod.resolve("all", self.root)), 4)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            targets_mod.resolve("bogus", self.root)

    def test_autodetect_defaults_to_claude(self):
        keys = [t.key for t in targets_mod.resolve(None, self.root)]
        self.assertEqual(keys, ["claude"])

    def test_autodetect_finds_opencode(self):
        (self.root / ".opencode").mkdir()
        keys = [t.key for t in targets_mod.resolve(None, self.root)]
        self.assertIn("opencode", keys)


class TestClaudeTarget(TempProject):
    def setUp(self):
        super().setUp()
        self.t = targets_mod.get("claude")

    def test_agents_copied_verbatim(self):
        self.t.emit_roles(self.root, SOME_ROLES)
        for slug in SOME_ROLES:
            got = (self.root / ".claude" / "agents" / f"{slug}.md").read_text(encoding="utf-8")
            want = (TEMPLATES / "agents" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertEqual(got, want)

    def test_hooks_written(self):
        added = self.t.emit_hooks(self.root)
        self.assertEqual(added, 2)
        sp = self.root / ".claude" / "settings.local.json"
        self.assertIn("cdt journal observe", sp.read_text(encoding="utf-8"))

    def test_guide_splice_preserves_user_notes(self):
        state1 = self.t.emit_guide(self.ctx())
        self.assertEqual(state1, "created")
        guide = self.root / "CLAUDE.md"
        guide.write_text(guide.read_text(encoding="utf-8") + "\nMY OWN NOTE\n", encoding="utf-8")
        state2 = self.t.emit_guide(self.ctx())
        self.assertEqual(state2, "synced")
        self.assertIn("MY OWN NOTE", guide.read_text(encoding="utf-8"))


class TestOpenCodeTarget(TempProject):
    def setUp(self):
        super().setUp()
        self.t = targets_mod.get("opencode")

    def test_agent_frontmatter_translated(self):
        self.t.emit_roles(self.root, ["software-architect"])
        meta, _ = base.split_frontmatter(
            (self.root / ".opencode" / "agents" / "software-architect.md").read_text(encoding="utf-8"))
        self.assertEqual(meta.get("mode"), "subagent")
        self.assertNotIn("name", meta)                       # filename carries the name
        self.assertTrue(meta.get("model", "").startswith("anthropic/"))

    def test_hook_plugin_idempotent(self):
        self.assertEqual(self.t.emit_hooks(self.root), 1)    # written once
        self.assertEqual(self.t.emit_hooks(self.root), 0)    # not re-written (user-editable)

    def test_opencode_json_instructions_no_dupe(self):
        self.t.emit_guide(self.ctx())
        self.t.emit_guide(self.ctx())                        # re-emit (sync)
        import json
        data = json.loads((self.root / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(data["instructions"].count("AGENTS.md"), 1)


class TestCodexPiSkills(TempProject):
    def test_codex_merges_into_agents_skills(self):
        targets_mod.get("codex").emit_roles(self.root, ["software-engineer"])
        skill = roles_mod.ROLES["software-engineer"].skill
        body = (self.root / ".agents" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Software Engineer", body)             # persona folded in
        self.assertIn("When to use", body)                   # skill steps folded in

    def test_pi_uses_pi_skills_and_prompt(self):
        pi = targets_mod.get("pi")
        pi.emit_roles(self.root, ["software-engineer"])
        self.assertTrue(pi.emit_driver(self.root))
        skill = roles_mod.ROLES["software-engineer"].skill
        self.assertTrue((self.root / ".pi" / "skills" / skill / "SKILL.md").is_file())
        self.assertTrue((self.root / ".pi" / "prompts" / "cdt.md").is_file())

    def test_pi_extension_captures_via_input(self):
        targets_mod.get("pi").emit_hooks(self.root)
        ext = (self.root / ".pi" / "extensions" / "conductor-honcho.ts").read_text(encoding="utf-8")
        self.assertIn("session_start", ext)
        self.assertIn("journal", ext)
        self.assertIn("observe", ext)


if __name__ == "__main__":
    unittest.main()
