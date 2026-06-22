# rag/ — semantic search over the library

Retrieves passages from the library books to **ground** the roles' answers
(fights hallucination).

## Stack

- **Embeddings:** `bge-m3` (1024-d, multilingual) served by local **Ollama**
  at `http://localhost:11434`. Access via `urllib` (stdlib) — no extra client.
- **Vector store:** persistent **ChromaDB** (cosine), at `rag/chroma/`
  (gitignored — built locally, not versioned).
- **Corpus:** markdown books from the public library repo
  (`eltonssouza/conductor-library`), fetched by `cdt up` into the stack. Host-side
  `library add|reindex` uses `CONDUCTOR_LIBRARY` (default `~/.conductor/library`).

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
cdt ingest                            # full library (in the Docker stack)
python -m conductor.rag.ingest --limit 200  # quick local sample

# Query
cdt library "bounded context boundaries"
cdt library -k 8 --json "circuit breaker vs bulkhead"
cdt library --category 09_seguranca_e_privacidade "STRIDE"
```

The generated project's `CLAUDE.md` tells the project's Claude to use
`cdt library` to anchor each gate.

## Configuration (environment variables)

| Var | Default | Purpose |
|-----|---------|---------|
| `CONDUCTOR_LIBRARY` | `~/.conductor/library` | host-side corpus root (`library add|reindex`) |
| `CONDUCTOR_LIBRARY_REPO` | `eltonssouza/conductor-library` | repo the corpus is fetched from on `cdt up` |
| `CONDUCTOR_LIBRARY_REF` | `main` | branch/tag of the library repo |
| `CONDUCTOR_LIBRARY_TIERS` | `core` | `software_dev` tiers to ingest (core/supporting/foundational/optional) |
| `CONDUCTOR_LIBRARY_STACKS` | _(none)_ | language/framework stacks to add (e.g. `python,angular`) or `all` |
| `CONDUCTOR_CHROMA` | `rag/chroma` | where to persist the index |
| `CONDUCTOR_EMBED_MODEL` | `bge-m3` | embeddings model in Ollama |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `CONDUCTOR_KEEP_ALIVE` | `30m` | how long Ollama keeps bge-m3 resident |
| `CONDUCTOR_HNSW_M` / `_CONSTRUCTION_EF` / `_SEARCH_EF` | `32` / `200` / `128` | HNSW index tuning |
| `CONDUCTOR_CHROMA_HTTP` | _(unset)_ | `host:port` of a resident Chroma server |

## Performance

Agent queries cost ≈ one bge-m3 embed + one HNSW search. Two levers keep that
low:

1. **bge-m3 resident on GPU** — `CONDUCTOR_KEEP_ALIVE` keeps the model loaded, so
   a query embeds in ~0.5s on GPU instead of ~2.4s cold. Verify with `ollama ps`
   (should read `100% GPU`).
2. **Resident Chroma server (optional)** — a fresh CLI process otherwise reloads
   the HNSW index from disk every query. Run a server once and point queries at
   it so the index stays in RAM:

   ```bash
   chroma run --path rag/chroma --port 8000          # leave running
   set CONDUCTOR_CHROMA_HTTP=localhost:8000           # then ingest/query hit it
   ```

HNSW recall/latency is tunable via the `CONDUCTOR_HNSW_*` vars (rebuild the index
after changing `M`/`construction_ef`; `search_ef` applies per query).
