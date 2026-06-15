# rag/ — semantic search over the library

Implements the RAG goal from `plano.md`: retrieve passages from the library
books to **ground** the roles' answers (fights hallucination).

## Stack

- **Embeddings:** `bge-m3` (1024-d, multilingual) served by local **Ollama**
  at `http://localhost:11434`. Access via `urllib` (stdlib) — no extra client.
- **Vector store:** persistent **ChromaDB** (cosine), at `rag/chroma/`
  (gitignored — built locally, not versioned).
- **Corpus:** markdown in `C:\development\to-brain` (configurable).

## Prerequisites

```bash
# 1. Ollama with the embeddings model
ollama pull bge-m3

# 2. Python dependency (optional project extra)
pip install -e .[rag]
```

## Usage

```bash
# Build/update the index (idempotent; can be resumed)
python -m rag.ingest                 # full library
python -m rag.ingest --limit 200     # quick sample

# Query
python -m rag.query "bounded context boundaries"
python -m rag.query -k 8 --json "circuit breaker vs bulkhead"
python -m rag.query --category 09_seguranca_e_privacidade "STRIDE"
```

Or via the plugin: command `/library <question>` (and `/cdt` uses the
library to anchor each gate).

## Configuration (environment variables)

| Var | Default | Purpose |
|-----|---------|---------|
| `CONDUCTOR_LIBRARY` | `C:\development\to-brain` | corpus markdown root |
| `CONDUCTOR_CHROMA` | `rag/chroma` | where to persist the index |
| `CONDUCTOR_EMBED_MODEL` | `bge-m3` | embeddings model in Ollama |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
