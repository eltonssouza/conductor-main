#!/usr/bin/env python3
"""Semantic search over the library. Embeds the question and returns the top-k passages.

  conductor library "how to define bounded context boundaries?"
  conductor library -k 8 --json "circuit breaker vs bulkhead"
  conductor library --category 09_seguranca_e_privacidade "STRIDE"
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from typing import List

from .rag.core import embed, force_utf8, get_collection


def _log_telemetry(question: str, k: int, category: str, hits: List[dict],
                   gate) -> None:
    """Best-effort: append one rag_query event to the project's telemetry log.

    Enables monitoring of the flow's "Ground" step (which gates actually
    consulted the library). Silent on any failure — never breaks a search.
    """
    try:
        from .project import find_project_root, memory_dir, read_config
        root = find_project_root()
        if read_config(root) is None:        # not an enrolled project
            return
        mem = memory_dir(root)
        mem.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "event": "rag_query",
            "gate": gate,
            "query": question,
            "k": k,
            "category": category or None,
            "n_hits": len(hits),
            "top_score": hits[0]["score"] if hits else None,
            "sources": sorted({h["source"] for h in hits if h.get("source")}),
        }
        with (mem / ".telemetry.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — telemetry must never break the query
        pass


def search(question: str, k: int = 5, category: str = "") -> List[dict]:
    coll = get_collection(create=False)
    where = {"category": category} if category else None
    res = coll.query(
        query_embeddings=embed([question]),
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({
            "score": round(1.0 - float(dist), 4),  # cosine: 1 - distance
            "source": meta.get("source", ""),
            "section": meta.get("section", ""),
            "category": meta.get("category", ""),
            "path": meta.get("path", ""),
            "text": doc,
        })
    return out


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Semantic search over the Conductor library.")
    ap.add_argument("question", help="question / query")
    ap.add_argument("-k", type=int, default=5, help="number of passages (default 5)")
    ap.add_argument("--category", default="", help="filter by library category")
    ap.add_argument("--gate", type=int, help="tag the query with a flow gate (telemetry)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)
    force_utf8()

    try:
        hits = search(args.question, k=args.k, category=args.category)
    except Exception as e:  # missing collection, Ollama down, etc.
        print(f"Search failed: {e}\nHint: run `python -m rag.ingest` and check Ollama.",
              file=sys.stderr)
        return 1

    _log_telemetry(args.question, args.k, args.category, hits, args.gate)

    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0

    if not hits:
        print("No passages found.")
        return 0
    for i, h in enumerate(hits, 1):
        loc = h["source"] + (f" — {h['section']}" if h["section"] else "")
        print(f"\n#{i}  [{h['score']:.3f}]  {loc}\n      {h['path']}")
        snippet = h["text"].strip().replace("\n", " ")
        print("      " + (snippet[:400] + ("…" if len(snippet) > 400 else "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
