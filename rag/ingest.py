#!/usr/bin/env python3
"""Indexa o acervo no ChromaDB: chunk → embed (bge-m3) → upsert.

Idempotente: re-rodar atualiza os mesmos chunk_ids (upsert), então pode ser
interrompido e retomado. Uso:

  python -m rag.ingest               # acervo inteiro
  python -m rag.ingest --limit 200   # só os N primeiros chunks (teste rápido)
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import List

from .core import (ACERVO_DIR, CHROMA_DIR, EMBED_BATCH, Chunk, embed,
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
    """Indexa um batch; se ele falhar, tenta por item e pula os ruins.

    Devolve quantos chunks foram realmente indexados.
    """
    try:
        _upsert(coll, batch, embed([c.text for c in batch]))
        return len(batch)
    except Exception as e:  # noqa: BLE001 — qualquer falha de rede/modelo
        print(f"  ! batch de {len(batch)} falhou ({e}); tentando item a item", file=sys.stderr)
        ok = 0
        for c in batch:
            try:
                _upsert(coll, [c], embed([c.text]))
                ok += 1
            except Exception as e2:  # noqa: BLE001
                print(f"  ! pulando chunk {c.chunk_id} ({e2})", file=sys.stderr)
        return ok


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Indexa o acervo no ChromaDB.")
    ap.add_argument("--limit", type=int, default=0, help="máx. de chunks (0 = todos)")
    ap.add_argument("--batch", type=int, default=EMBED_BATCH, help="tamanho do batch de embed")
    args = ap.parse_args(argv)
    force_utf8()

    if not ACERVO_DIR.is_dir():
        print(f"ERRO: acervo não encontrado em {ACERVO_DIR}", file=sys.stderr)
        return 2

    coll = get_collection(create=True)
    print(f"Acervo: {ACERVO_DIR}\nChroma: {CHROMA_DIR}\nColeção: {coll.name}")

    batch: List[Chunk] = []
    total = 0   # indexados com sucesso
    seen = 0    # processados (inclui pulados)
    t0 = time.monotonic()
    for chunk in iter_corpus():
        batch.append(chunk)
        seen += 1
        if len(batch) >= args.batch:
            total += _flush(coll, batch)
            batch = []
            if seen % (args.batch * 10) == 0:
                rate = seen / max(time.monotonic() - t0, 1e-6)
                print(f"  {seen} chunks processados, {total} indexados ({rate:.0f}/s)")
        if args.limit and seen >= args.limit:
            break

    if batch and (not args.limit or seen < args.limit):
        total += _flush(coll, batch)

    dt = time.monotonic() - t0
    print(f"Concluído: {seen} processados, {total} indexados em {dt:.0f}s. "
          f"Total na coleção: {coll.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
