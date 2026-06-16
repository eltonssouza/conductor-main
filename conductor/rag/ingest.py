#!/usr/bin/env python3
"""Indexes the library into ChromaDB: chunk → embed (bge-m3) → upsert.

Idempotent: re-running updates the same chunk_ids (upsert), so it can be
interrupted and resumed. Usage:

  python -m rag.ingest               # full library
  python -m rag.ingest --limit 200   # only the first N chunks (quick test)

Pipeline (golden rule 2): embedding (Ollama, the dominant cost) and the Chroma
upsert run on different threads — while batch N is upserted, batch N+1 is
already embedding. A single embed worker is enough: Ollama serializes a model
instance anyway, so the win is overlapping the (cheap) DB write with the
(expensive) next embed, not parallel embeds.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator, List, Tuple

from .core import (LIBRARY_DIR, CHROMA_DIR, EMBED_BATCH, Chunk, embed,
                   force_utf8, get_collection, iter_corpus)

# Per-batch embed telemetry: rate (chunks/s) reveals whether Ollama is the
# bottleneck and whether GPU/CPU is being saturated. Toggle with --quiet.
_VERBOSE = True

Pair = Tuple[Chunk, List[float]]


def _embed_batch(batch: List[Chunk]) -> List[Pair]:
    """Embeds a batch -> [(chunk, embedding)]. No DB access, so it is safe to
    run in a worker thread. On a batch failure, retries item by item and drops
    chunks that still fail (e.g. a single oversized/corrupt one)."""
    try:
        t0 = time.monotonic()
        embs = embed([c.text for c in batch])
        if _VERBOSE:
            dt = time.monotonic() - t0
            print(f"  embed {len(batch)} in {dt:.2f}s "
                  f"({len(batch)/max(dt,1e-6):.1f}/s)", file=sys.stderr)
        return list(zip(batch, embs))
    except Exception as e:  # noqa: BLE001 — any network/model failure
        print(f"  ! batch of {len(batch)} failed ({e}); retrying item by item",
              file=sys.stderr)
        pairs: List[Pair] = []
        for c in batch:
            try:
                pairs.append((c, embed([c.text])[0]))
            except Exception as e2:  # noqa: BLE001
                print(f"  ! skipping chunk {c.chunk_id} ({e2})", file=sys.stderr)
        return pairs


def _upsert_pairs(coll, pairs: List[Pair]) -> int:
    """Upserts embedded chunks into Chroma. Runs on the main thread."""
    if not pairs:
        return 0
    chunks = [c for c, _ in pairs]
    coll.upsert(
        ids=[c.chunk_id for c in chunks],
        embeddings=[e for _, e in pairs],
        documents=[c.text for c in chunks],
        metadatas=[{"source": c.source, "category": c.category,
                    "section": c.section, "path": c.path} for c in chunks],
    )
    return len(chunks)


def _iter_batches(size: int, limit: int) -> Iterator[List[Chunk]]:
    """Groups the streamed corpus into batches of `size`, honoring `limit`."""
    batch: List[Chunk] = []
    seen = 0
    for chunk in iter_corpus():
        batch.append(chunk)
        seen += 1
        if len(batch) >= size:
            yield batch
            batch = []
        if limit and seen >= limit:
            break
    if batch:
        yield batch


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Index the library into ChromaDB.")
    ap.add_argument("--limit", type=int, default=0, help="max chunks (0 = all)")
    ap.add_argument("--batch", type=int, default=EMBED_BATCH, help="embed batch size")
    ap.add_argument("--quiet", action="store_true", help="suppress per-batch telemetry")
    args = ap.parse_args(argv)
    force_utf8()
    global _VERBOSE
    _VERBOSE = not args.quiet

    if not LIBRARY_DIR.is_dir():
        print(f"ERROR: library not found at {LIBRARY_DIR}", file=sys.stderr)
        return 2

    coll = get_collection(create=True)
    print(f"Library: {LIBRARY_DIR}\nChroma: {CHROMA_DIR}\nCollection: {coll.name}")

    total = 0   # successfully indexed
    seen = 0    # processed (includes skipped)
    t0 = time.monotonic()

    # One embed worker; the main thread upserts the *previous* batch while the
    # next one embeds in the background.
    with ThreadPoolExecutor(max_workers=1) as ex:
        pending = None  # Future for the batch currently embedding
        for batch in _iter_batches(args.batch, args.limit):
            seen += len(batch)
            fut = ex.submit(_embed_batch, batch)
            if pending is not None:
                total += _upsert_pairs(coll, pending.result())
            pending = fut
            if seen % (args.batch * 10) == 0:
                rate = seen / max(time.monotonic() - t0, 1e-6)
                print(f"  {seen} chunks processed, {total} indexed ({rate:.1f}/s)")
        if pending is not None:
            total += _upsert_pairs(coll, pending.result())

    dt = time.monotonic() - t0
    print(f"Done: {seen} processed, {total} indexed in {dt:.0f}s. "
          f"Total in collection: {coll.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
