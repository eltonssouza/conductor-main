#!/usr/bin/env python3
"""Busca semântica no acervo. Embeda a pergunta e retorna os top-k trechos.

  python -m rag.query "como definir fronteiras de bounded context?"
  python -m rag.query -k 8 --json "circuit breaker vs bulkhead"
  python -m rag.query --category 09_seguranca_e_privacidade "STRIDE"
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .core import embed, force_utf8, get_collection


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
            "score": round(1.0 - float(dist), 4),  # cosine: 1 - distância
            "source": meta.get("source", ""),
            "section": meta.get("section", ""),
            "category": meta.get("category", ""),
            "path": meta.get("path", ""),
            "text": doc,
        })
    return out


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Busca semântica no acervo Conductor.")
    ap.add_argument("question", help="pergunta / consulta")
    ap.add_argument("-k", type=int, default=5, help="número de trechos (default 5)")
    ap.add_argument("--category", default="", help="filtra por categoria do acervo")
    ap.add_argument("--json", action="store_true", help="saída JSON")
    args = ap.parse_args(argv)
    force_utf8()

    try:
        hits = search(args.question, k=args.k, category=args.category)
    except Exception as e:  # coleção ausente, Ollama fora, etc.
        print(f"ERRO na busca: {e}\nDica: rode `python -m rag.ingest` e confira o Ollama.",
              file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0

    if not hits:
        print("Nenhum trecho encontrado.")
        return 0
    for i, h in enumerate(hits, 1):
        loc = h["source"] + (f" — {h['section']}" if h["section"] else "")
        print(f"\n#{i}  [{h['score']:.3f}]  {loc}\n      {h['path']}")
        snippet = h["text"].strip().replace("\n", " ")
        print("      " + (snippet[:400] + ("…" if len(snippet) > 400 else "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
