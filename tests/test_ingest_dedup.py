"""Test the ingest content-hash dedup and the final summary wording.

Chroma and Ollama are mocked, so this verifies the skip/index decision and the
DONE-line message without any heavy deps or network:

  - fresh/empty collection -> every chunk embedded + upserted (indexed, 0 skipped)
  - re-run on a populated collection -> every chunk skipped (0 indexed) and the
    DONE line reads as "already current", not as a failure
  - mixed (one chunk's text changed) -> only the changed chunk re-indexed
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from conductor.rag import ingest
from conductor.rag.core import Chunk


def _chunk(i: int, text: str) -> Chunk:
    return Chunk(chunk_id=f"book.md::{i}", text=text, source="book",
                 category="cat", section="", path="book.md")


class _FakeCollection:
    """Minimal stand-in for a Chroma collection: an in-memory id->metadata store
    that honours get(ids=...) / upsert(...) / count() the way ingest uses them."""

    def __init__(self, seed=None):
        self.store = dict(seed or {})  # chunk_id -> metadata

    def get(self, ids=None, include=None):
        ids = ids or []
        return {"ids": [i for i in ids if i in self.store],
                "metadatas": [self.store[i] for i in ids if i in self.store]}

    def upsert(self, ids, embeddings, documents, metadatas):
        for cid, meta in zip(ids, metadatas):
            self.store[cid] = meta

    def count(self):
        return len(self.store)

    name = "library"


def _fake_embed(texts):
    return [[0.0] * 4 for _ in texts]


class TestIngestDedup(unittest.TestCase):
    def _run(self, corpus, coll):
        buf = io.StringIO()
        with mock.patch.object(ingest, "get_collection", return_value=coll), \
             mock.patch.object(ingest, "embed", side_effect=_fake_embed), \
             mock.patch.object(ingest, "iter_corpus", return_value=iter(corpus)), \
             mock.patch.object(ingest, "LIBRARY_DIR") as lib, \
             redirect_stdout(buf):
            lib.is_dir.return_value = True
            rc = ingest.main(["--quiet", "--batch", "2"])
        return rc, buf.getvalue()

    def test_fresh_collection_indexes_everything(self):
        corpus = [_chunk(0, "alpha"), _chunk(1, "beta"), _chunk(2, "gamma")]
        coll = _FakeCollection()
        rc, out = self._run(corpus, coll)
        self.assertEqual(rc, 0)
        self.assertEqual(coll.count(), 3)
        self.assertIn("indexed 3 new chunks", out)

    def test_rerun_skips_everything_and_reads_as_current(self):
        corpus = [_chunk(0, "alpha"), _chunk(1, "beta"), _chunk(2, "gamma")]
        # Seed the collection as if a prior run already indexed the same text.
        seed = {c.chunk_id: {"chash": ingest._chash(c.text)} for c in corpus}
        coll = _FakeCollection(seed)
        rc, out = self._run(corpus, coll)
        self.assertEqual(rc, 0)
        self.assertEqual(coll.count(), 3)            # unchanged, nothing added
        self.assertIn("already current", out)        # not phrased as an error
        self.assertNotIn("indexed", out.split("Done")[-1])  # DONE line: no "indexed N"

    def test_partial_reindexes_only_changed(self):
        corpus = [_chunk(0, "alpha"), _chunk(1, "beta-CHANGED"), _chunk(2, "gamma")]
        # Prior run saw the OLD text of chunk 1 (so its chash differs now).
        seed = {
            corpus[0].chunk_id: {"chash": ingest._chash("alpha")},
            corpus[1].chunk_id: {"chash": ingest._chash("beta-OLD")},
            corpus[2].chunk_id: {"chash": ingest._chash("gamma")},
        }
        coll = _FakeCollection(seed)
        rc, out = self._run(corpus, coll)
        self.assertEqual(rc, 0)
        self.assertIn("indexed 1 new/changed chunks, 2 already current", out)


if __name__ == "__main__":
    unittest.main()
