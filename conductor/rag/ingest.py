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
import hashlib
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


def _chash(text: str) -> str:
    """Short content hash of a chunk's text — stored as `chash` metadata so a
    re-run can skip chunks whose text is unchanged (golden rule 3)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _filter_unchanged(coll, batch: List[Chunk]) -> List[Chunk]:
    """Drops chunks already in Chroma with a matching content hash. One get()
    round-trip per batch saves embedding ~all chunks on a re-run (embedding is
    orders of magnitude costlier than the lookup). On any error, embeds all."""
    ids = [c.chunk_id for c in batch]
    try:
        existing = coll.get(ids=ids, include=["metadatas"])
    except Exception as e:  # noqa: BLE001 — never let the lookup block ingest
        # Conservative: re-embed the whole batch. Surface a warning so a backend
        # problem isn't mistaken for a silent perf regression (dedup disabled).
        print(f"  ! dedup lookup failed ({e}); re-embedding this batch",
              file=sys.stderr)
        return batch
    have = {i: (m or {}).get("chash")
            for i, m in zip(existing.get("ids", []), existing.get("metadatas", []))}
    return [c for c in batch if have.get(c.chunk_id) != _chash(c.text)]


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
    try:
        coll.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=[e for _, e in pairs],
            documents=[c.text for c in chunks],
            metadatas=[{"source": c.source, "category": c.category,
                        "section": c.section, "path": c.path,
                        "chash": _chash(c.text)} for c in chunks],
        )
    except Exception as e:  # noqa: BLE001 — a swallowed upsert silently loses data
        # Never hide data loss: this batch of embeddings did NOT land in the
        # index. Surface it loudly and abort — a partial, silent index is worse
        # than a failed run the user can retry with `cdt up` / `cdt library reindex`.
        raise RuntimeError(
            f"Failed to upsert {len(chunks)} chunk(s) into ChromaDB — these are "
            f"NOT indexed. Is the stack up? Try: cdt up  ({e})"
        ) from e
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
    ap.add_argument("--force", action="store_true",
                    help="re-embed every chunk (skip the content-hash dedup)")
    args = ap.parse_args(argv)
    force_utf8()
    global _VERBOSE
    _VERBOSE = not args.quiet

    if not LIBRARY_DIR.is_dir():
        print(f"ERROR: library not found at {LIBRARY_DIR}", file=sys.stderr)
        return 2

    coll = get_collection(create=True)
    print(f"Library: {LIBRARY_DIR}\nChroma: {CHROMA_DIR}\nCollection: {coll.name}")

    total = 0     # successfully indexed (embedded + upserted)
    seen = 0      # processed (includes skipped)
    skipped = 0   # unchanged, skipped by the content-hash dedup
    t0 = time.monotonic()
    if not args.force:
        print("Incremental: skipping chunks unchanged since last ingest "
              "(use --force to re-embed all).")

    # One embed worker; the main thread upserts the *previous* batch while the
    # next one embeds in the background.
    with ThreadPoolExecutor(max_workers=1) as ex:
        pending = None  # Future for the batch currently embedding
        for batch in _iter_batches(args.batch, args.limit):
            seen += len(batch)
            fresh = batch if args.force else _filter_unchanged(coll, batch)
            skipped += len(batch) - len(fresh)
            fut = ex.submit(_embed_batch, fresh) if fresh else None
            if pending is not None:
                total += _upsert_pairs(coll, pending.result())
            pending = fut
            if seen % (args.batch * 10) == 0:
                rate = seen / max(time.monotonic() - t0, 1e-6)
                print(f"  {seen} processed, {total} indexed, {skipped} unchanged "
                      f"({rate:.1f}/s)")
        if pending is not None:
            total += _upsert_pairs(coll, pending.result())

    dt = time.monotonic() - t0
    in_coll = coll.count()
    # Make the final line read as a state, not an error. A run that indexes
    # nothing because everything was already current is the healthy re-run case
    # (content-hash dedup), not a failure — say so explicitly.
    if seen == 0:
        verdict = "library is empty — nothing to index"
    elif total == 0:
        verdict = f"index already current: {in_coll} chunks, nothing to do"
    elif skipped == 0:
        verdict = f"indexed {total} new chunks; collection now has {in_coll}"
    else:
        verdict = (f"indexed {total} new/changed chunks, {skipped} already current; "
                   f"collection now has {in_coll}")
    print(f"Done in {dt:.0f}s — {verdict}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
