#!/usr/bin/env python3
"""Semantic search over the library. Embeds the question and returns the top-k passages.

  cdt library "how to define bounded context boundaries?"
  cdt library -k 8 --json "circuit breaker vs bulkhead"
  cdt library --category 09_seguranca_e_privacidade "STRIDE"
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


def cmd_reindex(argv: List[str]) -> int:
    """Index every library file, skipping unchanged chunks (content-hash dedup).
    Catches files dropped straight into the library that were never embedded."""
    force_utf8()
    from .rag.ingest import main as ingest_main
    return ingest_main(argv)


def cmd_add(argv: List[str]) -> int:
    """Index one or more .md files already on disk under the library dir."""
    force_utf8()
    ap = argparse.ArgumentParser(prog="cdt library add",
                                 description="Index specific .md files into ChromaDB.")
    ap.add_argument("files", nargs="+", help="path(s) to .md file(s) under the library")
    args = ap.parse_args(argv)

    from pathlib import Path
    from .rag.core import LIBRARY_DIR, chunk_markdown, get_collection
    from .rag.ingest import _embed_batch, _upsert_pairs

    lib = LIBRARY_DIR.resolve()
    coll = get_collection(create=True)
    total = 0
    for raw in args.files:
        f = Path(raw).resolve()
        if not f.is_file():
            print(f"skip (not found): {raw}", file=sys.stderr)
            continue
        try:
            rel = f.relative_to(lib)
        except ValueError:
            print(f"skip (outside library {lib}): {raw}", file=sys.stderr)
            continue
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "(root)"
        chunks = chunk_markdown(f.read_text(encoding="utf-8"), source=f.stem,
                                category=category, path=str(rel).replace("\\", "/"))
        n = _upsert_pairs(coll, _embed_batch(chunks)) if chunks else 0
        total += n
        print(f"indexed {n} chunk(s): {rel}")
    print(f"Done: {total} chunk(s) upserted. Total in collection: {coll.count()}")
    return 0


def cmd_status(argv: List[str]) -> int:
    """Show what is actually ingested in the library index (books, categories,
    chunk counts) — so you can verify what `cdt up` downloaded for your stack."""
    force_utf8()
    ap = argparse.ArgumentParser(prog="cdt library status",
                                 description="What's in the library index right now.")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args(argv)

    try:
        coll = get_collection(create=False)
        total = coll.count()
    except Exception as e:  # noqa: BLE001 — Chroma down / collection missing
        print(f"Library index not reachable: {e}\n"
              "Hint: start the stack with `cdt up` first.", file=sys.stderr)
        return 1
    if total == 0:
        print("Library index is empty. Run `cdt up` to fetch + ingest the books.")
        return 0

    from collections import defaultdict
    data = coll.get(include=["metadatas"])          # small dicts; fine for a status
    books: dict = defaultdict(int)
    cats: dict = defaultdict(set)
    for m in (data.get("metadatas") or []):
        src, cat = m.get("source", "?"), m.get("category", "?")
        books[src] += 1
        cats[cat].add(src)

    if args.json:
        print(json.dumps({"chunks": total, "books": len(books),
                          "categories": {c: sorted(s) for c, s in cats.items()}},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"Library index: {total} chunks · {len(books)} books · {len(cats)} categories\n")
    for cat in sorted(cats):
        srcs = sorted(cats[cat])
        print(f"  {cat}/  ({len(srcs)} books)")
        for s in srcs:
            print(f"      {s}  ({books[s]} chunks)")
    return 0


def _library_json():
    from .project import REGISTRY_DIR
    return REGISTRY_DIR / "library.json"


def _current_stacks() -> List[str]:
    try:
        return list(json.loads(_library_json().read_text(encoding="utf-8")).get("stacks", []))
    except (OSError, ValueError):
        return []


def cmd_stacks(argv: List[str]) -> int:
    """Interactively choose which language/framework stacks to ingest.

    Lists the stacks available in the library repo (with versions), lets you pick,
    and saves the choice so the next `cdt up` ingests them. `--list` just prints."""
    force_utf8()
    ap = argparse.ArgumentParser(prog="cdt library stacks",
                                 description="Choose the technologies to ingest.")
    ap.add_argument("--list", action="store_true", help="just list; don't prompt")
    args = ap.parse_args(argv)

    from .rag.core import discover_stacks
    print("Fetching available technologies from the library repo...")
    avail = discover_stacks()
    if not avail:
        print("Could not reach the library repo. Check your connection / "
              "CONDUCTOR_LIBRARY_REPO.", file=sys.stderr)
        return 1

    # group by category folder (languages vs frameworks vs other)
    from collections import defaultdict
    groups: dict = defaultdict(list)
    order: List[str] = []
    for sid, info in avail.items():
        groups[info["category"]].append((sid, info["versions"]))
    current = _current_stacks()
    print(f"\nCurrently selected: {', '.join(current) or '(none — core only)'}\n")
    n = 0
    numbered: List[str] = []
    for cat in sorted(groups):
        label = cat.split("_", 1)[-1].replace("_", " ")
        print(f"  {label}:")
        for sid, vers in sorted(groups[cat]):
            n += 1
            numbered.append(sid)
            vtxt = f"  (versions: {', '.join(vers)})" if vers else ""
            mark = " *" if sid in current or any(c.split("@")[0] == sid for c in current) else ""
            print(f"    {n:>2}. {sid}{vtxt}{mark}")
    print()

    if args.list or not sys.stdin.isatty():
        print("Pick with: cdt library stacks  (interactive), or set "
              "CONDUCTOR_LIBRARY_STACKS=<ids> before `cdt up`.")
        return 0

    raw = input("Choose stacks to ingest (numbers/ids, comma-sep; `id@major` to pin a "
                "version; `all`; blank = keep current): ").strip()
    if not raw:
        print("Kept current selection.")
        return 0
    chosen: List[str] = []
    if raw.lower() == "all":
        chosen = sorted(avail)
    else:
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            base, _, ver = tok.partition("@")
            if base.isdigit():                       # a menu number
                idx = int(base) - 1
                if 0 <= idx < len(numbered):
                    sid = numbered[idx]
                    chosen.append(f"{sid}@{ver}" if ver else sid)
            elif base.lower() in avail:
                chosen.append(tok.lower())
            else:
                print(f"  (ignored unknown: {tok})", file=sys.stderr)
    chosen = sorted(dict.fromkeys(chosen))
    if not chosen:
        print("Nothing valid chosen; selection unchanged.", file=sys.stderr)
        return 1

    p = _library_json()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"stacks": chosen}, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved: {', '.join(chosen)}")
    print(f"  -> run `cdt up` to ingest them (the index accumulates; to start clean: "
          f"`cdt down; docker volume rm conductor_chroma; cdt up`).")
    return 0


def main(argv: List[str]) -> int:
    if argv and argv[0] == "reindex":
        return cmd_reindex(argv[1:])
    if argv and argv[0] == "add":
        return cmd_add(argv[1:])
    if argv and argv[0] == "status":
        return cmd_status(argv[1:])
    if argv and argv[0] == "stacks":
        return cmd_stacks(argv[1:])

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
