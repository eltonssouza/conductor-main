"""Test the generalized, provider-agnostic key resolution in honcho_setup.

Order (highest precedence first): --api-key > env var (CONDUCTOR_<P>_API_KEY or
the preset key_env) > per-provider key file > None (caller prompts/placeholder).
Filesystem and env are mocked — no network, no real files.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from conductor import honcho_setup as hs


class TestKeyFilePath(unittest.TestCase):
    def test_default_per_provider_path(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch.object(hs.Path, "home", return_value=hs.Path("/home/u")):
            p = hs._key_file_for("openrouter")
        self.assertEqual(p, hs.Path("/home/u") / ".conductor" / "openrouter-key.txt")

    def test_per_provider_env_override(self):
        with mock.patch.dict("os.environ",
                             {"CONDUCTOR_OPENAI_API_KEY_FILE": "/tmp/oai.txt"}, clear=True):
            self.assertEqual(hs._key_file_for("openai"), hs.Path("/tmp/oai.txt"))

    def test_legacy_deepseek_env_override_still_works(self):
        with mock.patch.dict("os.environ",
                             {"CONDUCTOR_DEEPSEEK_KEY_FILE": "/legacy/ds.txt"}, clear=True):
            self.assertEqual(hs._key_file_for("deepseek"), hs.Path("/legacy/ds.txt"))


class TestReadKeyFromFile(unittest.TestCase):
    def _read(self, text, var=None):
        with mock.patch.object(hs.Path, "read_text", return_value=text):
            return hs._read_key_from_file(hs.Path("x"), var)

    def test_legacy_deepseek_named_var(self):
        self.assertEqual(
            self._read('API-KEY-DEEP_SEEK: "sk-deadbeef0000"', hs.DEEPSEEK_KEY_VAR),
            "sk-deadbeef0000")

    def test_bare_token_line(self):
        self.assertEqual(self._read("sk-or-v1-abcdef123456"), "sk-or-v1-abcdef123456")

    def test_name_equals_value(self):
        self.assertEqual(self._read("OPENAI_KEY=sk-aaaa1111bbbb2222"),
                         "sk-aaaa1111bbbb2222")

    def test_comment_ignored(self):
        self.assertIsNone(self._read("# sk-shouldnotmatch00\n"))

    def test_missing_file_returns_none(self):
        with mock.patch.object(hs.Path, "read_text", side_effect=OSError):
            self.assertIsNone(hs._read_key_from_file(hs.Path("nope"), None))


class TestResolveKey(unittest.TestCase):
    PRESET = hs.PRESETS["deepseek"]

    def _resolve(self, provider, cli_key, env=None, file_key=None):
        # Keep a home dir resolvable on all platforms (used to build the key-file
        # path even when the read is mocked).
        env = {"HOME": "/home/u", "USERPROFILE": r"C:\Users\u", **(env or {})}
        buf = io.StringIO()
        with mock.patch.dict("os.environ", env, clear=True), \
             mock.patch.object(hs, "_read_key_from_file", return_value=file_key), \
             redirect_stdout(buf):
            return hs._resolve_key(provider, hs.PRESETS[provider], cli_key)

    def test_cli_key_wins(self):
        self.assertEqual(
            self._resolve("deepseek", "sk-cli", env={"LLM_OPENAI_API_KEY": "sk-env"},
                          file_key="sk-file"),
            "sk-cli")

    def test_per_provider_env_var(self):
        self.assertEqual(
            self._resolve("deepseek", None,
                          env={"CONDUCTOR_DEEPSEEK_API_KEY": "sk-pp"}, file_key="sk-file"),
            "sk-pp")

    def test_preset_key_env_fallback(self):
        self.assertEqual(
            self._resolve("openai", None, env={"LLM_OPENAI_API_KEY": "sk-preset"},
                          file_key="sk-file"),
            "sk-preset")

    def test_file_when_no_cli_or_env(self):
        self.assertEqual(self._resolve("openrouter", None, env={}, file_key="sk-or-file"),
                         "sk-or-file")

    def test_none_when_nothing(self):
        self.assertIsNone(self._resolve("custom", None, env={}, file_key=None))


class TestCustomProvider(unittest.TestCase):
    def test_custom_requires_base_url(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hs.main(["--provider", "custom", "--model", "m",
                          "--api-key", "sk-x", "--out", "/tmp/none.env"])
        self.assertEqual(rc, 2)

    def test_custom_requires_model(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hs.main(["--provider", "custom", "--base-url", "https://gw/v1",
                          "--api-key", "sk-x", "--out", "/tmp/none.env"])
        self.assertEqual(rc, 2)


class TestRenderEnv(unittest.TestCase):
    def test_ollama_embeddings_stay_local(self):
        env = hs.render_env("ollama", "qwen2.5:3b",
                            "http://host.docker.internal:11434/v1", "ollama",
                            "LLM_OPENAI_API_KEY", "openai")
        self.assertIn("EMBEDDING_MODEL_CONFIG__MODEL=bge-m3", env)
        self.assertIn("EMBEDDING_VECTOR_DIMENSIONS=1024", env)
        self.assertIn("EMBEDDING_MODEL_CONFIG__DIMENSIONS_MODE=never", env)

    def test_custom_embeddings_stay_local(self):
        env = hs.render_env("custom", "my-model", "https://gw/v1", "sk-x",
                            "LLM_OPENAI_API_KEY", "openai")
        self.assertIn("EMBEDDING_MODEL_CONFIG__MODEL=bge-m3", env)
        self.assertIn("LLM_OPENAI_BASE_URL=https://gw/v1", env)

    def test_openai_uses_openai_embeddings(self):
        env = hs.render_env("openai", "gpt-4o-mini", "https://api.openai.com/v1",
                            "sk-x", "LLM_OPENAI_API_KEY", "openai")
        self.assertIn("EMBEDDING_MODEL_CONFIG__MODEL=text-embedding-3-small", env)
        self.assertIn("EMBEDDING_VECTOR_DIMENSIONS=1536", env)

    def test_anthropic_transport(self):
        env = hs.render_env("anthropic", "claude-haiku-4-5", "", "sk-ant-x",
                            "LLM_ANTHROPIC_API_KEY", "anthropic")
        self.assertIn("DERIVER_MODEL_CONFIG__TRANSPORT=anthropic", env)
        self.assertIn("LLM_ANTHROPIC_API_KEY=sk-ant-x", env)
        self.assertNotIn("LLM_OPENAI_BASE_URL", env)


if __name__ == "__main__":
    unittest.main()
