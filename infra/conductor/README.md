# infra/conductor — the RAG stack in Docker (Ollama + bge-m3 + ChromaDB)

Brings the library RAG online end to end and **shows the progress** of each step.
Three services:

| Service | Role | Port (localhost) |
|---------|------|------------------|
| `ollama` | serves the `bge-m3` embedding model | 11434 |
| `chroma` | the ChromaDB vector store (persistent) | 8001 |
| `conductor` | one-shot bootstrap: extract books → pull model → ingest | — |

## Use it

```bash
# 1. Point at the books archive — either drop it here as to-brain.7z:
cp /path/to/to-brain.7z infra/conductor/to-brain.7z
#    ...or keep it elsewhere and set CONDUCTOR_ARCHIVE (path relative to
#    infra/conductor/), e.g. the repo root:  CONDUCTOR_ARCHIVE=../../to-brain.7z

# 2. Bring the stack up (attached, to watch progress)
cd infra/conductor
docker compose up                       # uses ./to-brain.7z
#   repo-root archive:  CONDUCTOR_ARCHIVE=../../to-brain.7z docker compose up
#   detached:           docker compose up -d && docker compose logs -f conductor
```

The `conductor` service prints:

```
[1/4] extracting to-brain.7z -> /data/library ... 136 .md books
[2/4] pulling bge-m3:  73.4%
[3/4] ChromaDB is up
[4/4] ingesting books from /data/library into ChromaDB (chroma:8000)
  640 chunks processed, 640 indexed (38/s)
  ...
[done] RAG stack ready
```

It **exits when the ingest finishes**; `ollama` and `chroma` keep running to
serve queries. It is idempotent — re-running skips a populated library, skips an
already-pulled model, and upserts the ingest (so an interrupted run resumes).

## Querying after the build

From the host, point the RAG query at the containerized Chroma + Ollama:

```bash
set CONDUCTOR_CHROMA_HTTP=localhost:8001
set OLLAMA_HOST=http://localhost:11434
python -m rag.query "bounded context"
```

## GPU (recommended)

CPU embedding of the full corpus takes **hours**. With an NVIDIA GPU + the
NVIDIA Container Toolkit, uncomment the `deploy:` block under `ollama` in
`docker-compose.yml` to run bge-m3 on the GPU (~0.5 s/embed, like the local dev
setup). Verify with `docker compose exec ollama ollama ps` (should read GPU).

## Notes

- `to-brain.7z` is gitignored (it is the corpus, not source). Zip the **category
  folders** (e.g. `08_sistemas_distribuidos/…`) at the archive root so the
  ingest keeps the right `category` metadata.
- Port 8001 is used for Chroma so it does not clash with Honcho on 8000
  (`infra/honcho/`).
- This stack is independent from the Honcho diary stack; run either or both.
