"""Núcleo do RAG do Conductor.

Pipeline: markdown do acervo → chunks → embeddings bge-m3 (via Ollama) →
ChromaDB persistente. Compartilhado pelos CLIs `ingest.py` e `query.py`.

Dependências de runtime (decisão do dono, 2026-06-14):
- Ollama servindo `bge-m3` em http://localhost:11434 (embeddings 1024-d).
- chromadb como vector store.

O acesso ao Ollama usa só urllib (stdlib); só o ChromaDB é de terceiros.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


def force_utf8() -> None:
    """Garante stdout/stderr em UTF-8 (console Windows usa cp1252 por padrão)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

# --- configuração ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ACERVO_DIR = Path(os.environ.get("CONDUCTOR_ACERVO", r"C:\development\to-brain"))
CHROMA_DIR = Path(os.environ.get("CONDUCTOR_CHROMA", str(REPO_ROOT / "rag" / "chroma")))
COLLECTION = "acervo"

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.environ.get("CONDUCTOR_EMBED_MODEL", "bge-m3")
EMBED_DIM = 1024

# Chunking: alvo em caracteres (~512 tokens) com sobreposição de 1 parágrafo.
CHUNK_TARGET_CHARS = 1500
CHUNK_MAX_CHARS = 2400
EMBED_BATCH = 48
# Teto de segurança por texto enviado ao Ollama (bge-m3 ~8192 tokens). Acima
# disso o /api/embed devolve HTTP 400; truncamos para nunca estourar.
EMBED_CHAR_CAP = 6000


# --- chunking ----------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str       # nome do arquivo (livro)
    category: str     # diretório de topo
    section: str      # último heading markdown visto
    path: str         # caminho relativo ao acervo


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")


def chunk_markdown(text: str, *, source: str, category: str, path: str) -> List[Chunk]:
    """Quebra markdown em chunks por parágrafos, empacotando até ~alvo de chars.

    Mantém o último heading como `section` para dar contexto ao trecho.
    """
    chunks: List[Chunk] = []
    section = ""
    buf: List[str] = []
    buf_len = 0
    idx = 0

    def flush():
        nonlocal buf, buf_len, idx
        if not buf:
            return
        body = "\n\n".join(buf).strip()
        if body:
            chunks.append(Chunk(
                chunk_id=f"{path}::{idx}",
                text=(f"[{source} — {section}]\n{body}" if section else f"[{source}]\n{body}"),
                source=source, category=category, section=section, path=path,
            ))
            idx += 1
        buf, buf_len = [], 0

    # parágrafos separados por linha em branco; parágrafos gigantes (tabelas,
    # blocos de código sem linha em branco) são fatiados para não estourar o
    # contexto do modelo de embeddings.
    raw_paras = re.split(r"\n\s*\n", text)
    paras: List[str] = []
    for p in raw_paras:
        p = p.strip()
        if not p:
            continue
        if len(p) > CHUNK_MAX_CHARS:
            paras.extend(p[i:i + CHUNK_MAX_CHARS] for i in range(0, len(p), CHUNK_MAX_CHARS))
        else:
            paras.append(p)

    for para in paras:
        m = _HEADING_RE.match(para.splitlines()[0])
        if m:
            section = m.group(1).strip()[:120]
        plen = len(para)
        if buf_len + plen > CHUNK_TARGET_CHARS and buf:
            tail = buf[-1] if buf_len + plen <= CHUNK_MAX_CHARS else None
            flush()
            if tail and len(tail) < CHUNK_TARGET_CHARS // 2:
                buf, buf_len = [tail], len(tail)  # sobreposição leve
        buf.append(para)
        buf_len += plen
        if buf_len >= CHUNK_MAX_CHARS:
            flush()
    flush()
    return chunks


def iter_corpus(acervo: Path = ACERVO_DIR) -> Iterable[Chunk]:
    """Percorre `acervo/**/*.md` e gera todos os chunks."""
    for md in sorted(acervo.rglob("*.md")):
        rel = md.relative_to(acervo)
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "(raiz)"
        text = md.read_text(encoding="utf-8", errors="replace")
        yield from chunk_markdown(
            text, source=md.stem, category=category, path=str(rel).replace("\\", "/"),
        )


# --- embeddings (Ollama bge-m3) ---------------------------------------------

def embed(texts: List[str]) -> List[List[float]]:
    """Embeda uma lista de textos via Ollama /api/embed (batch). 1024-d.

    Cada texto é truncado em EMBED_CHAR_CAP e o vazio vira espaço, para nunca
    provocar HTTP 400 do Ollama.
    """
    safe = [(t[:EMBED_CHAR_CAP] or " ") for t in texts]
    payload = json.dumps({"model": EMBED_MODEL, "input": safe}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise RuntimeError(f"Ollama retornou {len(embs or [])} embeddings para {len(texts)} textos")
    return embs


# --- ChromaDB ----------------------------------------------------------------

def get_collection(create: bool = True):
    """Abre (ou cria) a coleção persistente do acervo."""
    import chromadb  # import tardio: dependência pesada

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if create:
        return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return client.get_collection(COLLECTION)
