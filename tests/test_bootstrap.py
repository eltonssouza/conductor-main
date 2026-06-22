"""Tests for the library-repo corpus fetch (offline).

Builds a synthetic GitHub-style tarball in memory and monkeypatches `urlopen`,
so the strip/skip/path-guard logic of `_fetch_repo_corpus` is verified without
any network.
"""
import gzip
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from conductor.rag import bootstrap


def _member(tf, name, data=b"# book\n"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def _fake_tarball():
    """A `conductor-library-main/` tree: two real books, a root meta doc, and a
    traversal attempt that must be ignored."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        _member(tf, "conductor-library-main/06_web/angular.md")
        _member(tf, "conductor-library-main/06_web/sub/forms.md")
        _member(tf, "conductor-library-main/README.md")            # root meta -> skip
        _member(tf, "conductor-library-main/../evil.md")           # traversal -> skip
    return gzip.compress(raw.getvalue())


class _FakeResp:
    def __init__(self, blob):
        self._blob = blob
    def read(self):
        return self._blob
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class TestFetchCorpus(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lib = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_extracts_books_skips_meta_and_traversal(self):
        blob = _fake_tarball()
        with mock.patch.object(bootstrap, "LIBRARY", self.lib), \
             mock.patch.object(bootstrap.urllib.request, "urlopen",
                               return_value=_FakeResp(blob)):
            bootstrap._fetch_repo_corpus()

        mds = sorted(p.relative_to(self.lib).as_posix() for p in self.lib.rglob("*.md"))
        self.assertEqual(mds, ["06_web/angular.md", "06_web/sub/forms.md"])
        self.assertFalse((self.lib / "README.md").exists())        # root meta skipped
        self.assertFalse((self.lib.parent / "evil.md").exists())   # traversal blocked

    def test_network_failure_leaves_library_empty(self):
        with mock.patch.object(bootstrap, "LIBRARY", self.lib), \
             mock.patch.object(bootstrap.urllib.request, "urlopen",
                               side_effect=OSError("no network")):
            bootstrap._fetch_repo_corpus()  # must not raise
        self.assertEqual(list(self.lib.rglob("*.md")), [])


def _tagged_tarball():
    """A repo tree: one agnostic core book + three stack books (java/angular/ruby)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        _member(tf, "conductor-library-main/03_design/clean.md",
                b"---\nsoftware_dev: core\n---\n\n# Clean\n")
        for lang in ("java", "angular", "ruby"):
            _member(tf, f"conductor-library-main/lang/{lang}.md",
                    f"---\nsoftware_dev: stack\nstack: {lang}\n---\n\n# {lang}\n".encode())
    return gzip.compress(raw.getvalue())


class TestSelectiveFetch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lib = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_extracts_only_chosen_stacks(self):
        from conductor.rag import core
        with mock.patch.object(bootstrap, "LIBRARY", self.lib), \
             mock.patch.object(bootstrap.urllib.request, "urlopen",
                               return_value=_FakeResp(_tagged_tarball())), \
             mock.patch.object(core, "LIBRARY_TIERS", ["core"]), \
             mock.patch.object(core, "LIBRARY_STACKS", ["java", "angular"]):
            bootstrap._fetch_repo_corpus()
        got = sorted(p.name for p in self.lib.rglob("*.md"))
        self.assertEqual(got, ["angular.md", "clean.md", "java.md"])  # ruby NOT downloaded


if __name__ == "__main__":
    unittest.main()
