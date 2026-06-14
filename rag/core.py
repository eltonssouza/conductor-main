"""Core of the Conductor RAG.

Pipeline: acervo markdown → chunks → bge-m3 embeddings (via Ollama) →
persistent ChromaDB. Shared by the `ingest.py` and `query.py` CLIs.

Runtime dependencies (owner decision, 2026-06-14):
- Ollama serving `bge-m3` at http://localhost:11434 (1024-d embeddings).
- chromadb as the vector store.

Ollama access uses only urllib (stdlib); only ChromaDB is third-party.
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
    """Ensures stdout/stderr use UTF-8 (Windows console defaults to cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

# --- configuration -----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ACERVO_DIR = Path(os.environ.get("CONDUCTOR_ACERVO", r"C:\development\to-brain"))
CHROMA_DIR = Path(os.environ.get("CONDUCTOR_CHROMA", str(REPO_ROOT / "rag" / "chroma")))
COLLECTION = "acervo"

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.environ.get("CONDUCTOR_EMBED_MODEL", "bge-m3")
EMBED_DIM = 1024

# Chunking: target in characters (~512 tokens) with 1-paragraph overlap.
CHUNK_TARGET_CHARS = 1500
CHUNK_MAX_CHARS = 2400
EMBED_BATCH = 48
# Safety cap per text sent to Ollama (bge-m3 ~8192 tokens). Above this,
# /api/embed returns HTTP 400; we truncate to never overflow.
EMBED_CHAR_CAP = 6000


# --- chunking ----------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str       # file name (book)
    category: str     # top-level directory
    section: str      # last markdown heading seen
    path: str         # path relative to the acervo


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
# Control chars except tab/newline/carriage-return. NUL bytes (UTF-16 leftovers
# in some corpus files) make Ollama /api/embed return HTTP 400, so we strip them.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize(text: str) -> str:
    """Removes NUL and other C0 control chars that break the embeddings API."""
    return _CTRL_RE.sub("", text)


def chunk_markdown(text: str, *, source: str, category: str, path: str) -> List[Chunk]:
    """Splits markdown into chunks by paragraphs, packing up to ~target chars.

    Tracks the last heading as `section` to provide context for each chunk.
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

    # paragraphs separated by blank lines; oversized paragraphs (tables,
    # code blocks without blank lines) are sliced to avoid overflowing the
    # embedding model's context.
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
                buf, buf_len = [tail], len(tail)  # light overlap
        buf.append(para)
        buf_len += plen
        if buf_len >= CHUNK_MAX_CHARS:
            flush()
    flush()
    return chunks


def iter_corpus(acervo: Path = ACERVO_DIR) -> Iterable[Chunk]:
    """Walks `acervo/**/*.md` and yields all chunks."""
    for md in sorted(acervo.rglob("*.md")):
        rel = md.relative_to(acervo)
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "(root)"
        text = sanitize(md.read_text(encoding="utf-8", errors="replace"))
        yield from chunk_markdown(
            text, source=md.stem, category=category, path=str(rel).replace("\\", "/"),
        )


# --- embeddings (Ollama bge-m3) ---------------------------------------------

def embed(texts: List[str]) -> List[List[float]]:
    """Embeds a list of texts via Ollama /api/embed (batch). 1024-d.

    Each text is truncated to EMBED_CHAR_CAP and empty strings become a space,
    so Ollama never returns HTTP 400.
    """
    safe = [(sanitize(t)[:EMBED_CHAR_CAP] or " ") for t in texts]
    payload = json.dumps({"model": EMBED_MODEL, "input": safe}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise RuntimeError(f"Ollama returned {len(embs or [])} embeddings for {len(texts)} texts")
    return embs


# --- ChromaDB ----------------------------------------------------------------

def get_collection(create: bool = True):
    """Opens (or creates) the persistent acervo collection."""
    import chromadb  # late import: heavy dependency

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if create:
        return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return client.get_collection(COLLECTION)
