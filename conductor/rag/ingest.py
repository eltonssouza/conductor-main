#!/usr/bin/env python3
"""Indexes the library into ChromaDB: chunk → embed (bge-m3) → upsert.

Idempotent: re-running updates the same chunk_ids (upsert), so it can be
interrupted and resumed. Usage:

  python -m rag.ingest               # full library
  python -m rag.ingest --limit 200   # only the first N chunks (quick test)
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import List

from .core import (LIBRARY_DIR, CHROMA_DIR, EMBED_BATCH, Chunk, embed,
                   force_utf8, get_collection, iter_corpus)


def _upsert(coll, batch: List[Chunk], embs) -> None:
    coll.upsert(
        ids=[c.chunk_id for c in batch],
        embeddings=embs,
        documents=[c.text for c in batch],
        metadatas=[{"source": c.source, "category": c.category,
                    "section": c.section, "path": c.path} for c in batch],
    )


def _flush(coll, batch: List[Chunk]) -> int:
    """Indexes a batch; if it fails, retries item-by-item and skips bad ones.

    Returns the number of chunks actually indexed.
    """
    try:
        _upsert(coll, batch, embed([c.text for c in batch]))
        return len(batch)
    except Exception as e:  # noqa: BLE001 — any network/model failure
        print(f"  ! batch of {len(batch)} failed ({e}); retrying item by item", file=sys.stderr)
        ok = 0
        for c in batch:
            try:
                _upsert(coll, [c], embed([c.text]))
                ok += 1
            except Exception as e2:  # noqa: BLE001
                print(f"  ! skipping chunk {c.chunk_id} ({e2})", file=sys.stderr)
        return ok


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Index the library into ChromaDB.")
    ap.add_argument("--limit", type=int, default=0, help="max chunks (0 = all)")
    ap.add_argument("--batch", type=int, default=EMBED_BATCH, help="embed batch size")
    args = ap.parse_args(argv)
    force_utf8()

    if not LIBRARY_DIR.is_dir():
        print(f"ERROR: library not found at {LIBRARY_DIR}", file=sys.stderr)
        return 2

    coll = get_collection(create=True)
    print(f"Library: {LIBRARY_DIR}\nChroma: {CHROMA_DIR}\nCollection: {coll.name}")

    batch: List[Chunk] = []
    total = 0   # successfully indexed
    seen = 0    # processed (includes skipped)
    t0 = time.monotonic()
    for chunk in iter_corpus():
        batch.append(chunk)
        seen += 1
        if len(batch) >= args.batch:
            total += _flush(coll, batch)
            batch = []
            if seen % (args.batch * 10) == 0:
                rate = seen / max(time.monotonic() - t0, 1e-6)
                print(f"  {seen} chunks processed, {total} indexed ({rate:.0f}/s)")
        if args.limit and seen >= args.limit:
            break

    if batch and (not args.limit or seen < args.limit):
        total += _flush(coll, batch)

    dt = time.monotonic() - t0
    print(f"Done: {seen} processed, {total} indexed in {dt:.0f}s. "
          f"Total in collection: {coll.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
