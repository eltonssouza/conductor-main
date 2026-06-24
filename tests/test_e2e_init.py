"""Black-box end-to-end tests for `cdt init` (and a follow-up `sync`).

Pure stdlib (`unittest`), fully hermetic: no Docker, no network, no Ollama, no
optional extras. Each test scaffolds a minimal fake project into a temp dir,
drives the public CLI entry point (`conductor.cli.main`), and asserts the
artifacts the default Claude target actually writes (per `scaffold.py` and
`targets/claude.py`).

The global enrolled-projects registry is redirected to a temp dir via the
`CONDUCTOR_HOME` env var (read by `conductor.project`) so the suite never
touches the real `~/.claude/conductor/projects.json`.

Run: `python -m unittest tests.test_e2e_init -v`
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from conductor.cli import main


class E2EInitBase(unittest.TestCase):
    """A temp project (pyproject.toml -> detected as a Python backend) plus a
    redirected global registry, so init/sync run without side effects."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # Minimal manifest so detect() classifies this as a backend (Python).
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "fake-proj"\nrequires-python = ">=3.10"\n',
            encoding="utf-8",
        )

        # Keep the global registry write hermetic.
        self._reg = tempfile.TemporaryDirectory()
        self.addCleanup(self._reg.cleanup)
        self._prev_home = os.environ.get("CONDUCTOR_HOME")
        os.environ["CONDUCTOR_HOME"] = self._reg.name
        self.addCleanup(self._restore_home)

    def _restore_home(self):
        if self._prev_home is None:
            os.environ.pop("CONDUCTOR_HOME", None)
        else:
            os.environ["CONDUCTOR_HOME"] = self._prev_home

    def run_cli(self, *argv):
        """Invoke the CLI, swallowing its progress output. Returns the exit code."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()


class TestInitClaudeArtifacts(E2EInitBase):
    def test_init_scaffolds_default_claude_target(self):
        code, _ = self.run_cli("init", str(self.root))
        self.assertEqual(code, 0)

        # 1. Agents and skills are populated.
        agents = self.root / ".claude" / "agents"
        skills = self.root / ".claude" / "skills"
        self.assertTrue(agents.is_dir(), ".claude/agents/ should exist")
        self.assertTrue(skills.is_dir(), ".claude/skills/ should exist")

        agent_files = list(agents.glob("*.md"))
        skill_files = list(skills.glob("*/SKILL.md"))
        self.assertGreater(len(agent_files), 0, "expected role agents")
        self.assertGreater(len(skill_files), 0, "expected matching skills")
        # 1:1 pairing — one SKILL.md per agent.
        self.assertEqual(len(agent_files), len(skill_files))

        # 2. The Claude guide (CLAUDE.md) is written, with the managed region.
        guide = self.root / "CLAUDE.md"
        self.assertTrue(guide.is_file(), "CLAUDE.md guide should be written")
        text = guide.read_text(encoding="utf-8")
        self.assertIn("<!-- conductor:managed:start", text)
        self.assertIn("<!-- conductor:managed:end -->", text)

        # 3. .cdt/config.json records the chosen (claude) target + detected type.
        cfg_path = self.root / ".cdt" / "config.json"
        self.assertTrue(cfg_path.is_file(), ".cdt/config.json should exist")
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(cfg["targets"], ["claude"])
        self.assertEqual(cfg["type"], "backend")
        # Slug defaults to the slugified project directory name.
        from conductor.project import slugify
        self.assertEqual(cfg["project"], slugify(self.root.name))
        self.assertEqual(sorted(cfg["roles"]), sorted(p.stem for p in agent_files))

        # 4. The .cdt/ memory tree and stack file exist.
        memory = self.root / ".cdt" / "memory"
        self.assertTrue((memory / "_index.md").is_file())
        self.assertTrue((memory / "diary").is_dir())
        self.assertTrue((memory / "docs" / "architecture" / "_index.md").is_file())
        self.assertTrue((memory / "records" / "decisions" / "_index.md").is_file())
        self.assertTrue((self.root / ".cdt" / "stack" / "backend.md").is_file())

        # The /cdt driver is installed for the Claude target.
        self.assertTrue((self.root / ".claude" / "commands" / "cdt.md").is_file())


class TestInitIdempotency(E2EInitBase):
    def test_second_init_is_noop_without_force(self):
        code1, _ = self.run_cli("init", str(self.root))
        self.assertEqual(code1, 0)
        # A second init on an already-enrolled project exits 0 and does nothing.
        code2, out2 = self.run_cli("init", str(self.root))
        self.assertEqual(code2, 0)
        self.assertIn("Already enrolled", out2)

    def test_sync_preserves_user_notes_below_managed_region(self):
        code, _ = self.run_cli("init", str(self.root))
        self.assertEqual(code, 0)

        guide = self.root / "CLAUDE.md"
        marker = "MY OWN HAND-WRITTEN NOTE BELOW THE MANAGED REGION"
        guide.write_text(
            guide.read_text(encoding="utf-8") + f"\n\n{marker}\n",
            encoding="utf-8",
        )

        # `sync` re-emits the managed region but must keep the human's text.
        code_sync, _ = self.run_cli("sync", str(self.root))
        self.assertEqual(code_sync, 0)

        after = guide.read_text(encoding="utf-8")
        self.assertIn(marker, after)
        self.assertIn("<!-- conductor:managed:start", after)
        self.assertIn("<!-- conductor:managed:end -->", after)
        # The note stays below the managed region's end marker.
        self.assertGreater(after.index(marker), after.index("<!-- conductor:managed:end -->"))

    def test_double_sync_does_not_error_or_duplicate_notes(self):
        self.run_cli("init", str(self.root))
        guide = self.root / "CLAUDE.md"
        marker = "STABLE USER NOTE"
        guide.write_text(guide.read_text(encoding="utf-8") + f"\n{marker}\n",
                         encoding="utf-8")
        for _ in range(2):
            code, _ = self.run_cli("sync", str(self.root))
            self.assertEqual(code, 0)
        self.assertEqual(guide.read_text(encoding="utf-8").count(marker), 1)


if __name__ == "__main__":
    unittest.main()
