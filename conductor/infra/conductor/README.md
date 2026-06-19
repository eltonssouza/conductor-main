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
# Recommended: the launcher auto-detects the GPU and the books archive.
cdt up                     # attached (watch progress)
cdt up -d                  # detached  (then: docker compose logs -f conductor)
cdt down                   # stop
```

The launcher (`conductor/rag/stack.py`, invoked by `cdt up`):
- **detects an NVIDIA GPU** (`nvidia-smi`) **and Docker's NVIDIA runtime** — if
  both are present it adds `docker-compose.gpu.yml` so Ollama uses the GPU; if
  not, it says so and runs on CPU (slow). It prints which mode it chose.
- **auto-locates the books archive**: a `to-brain.7z` in `infra/conductor/` or at
  the repo root is used automatically; otherwise set `CONDUCTOR_ARCHIVE`.

Plain Docker still works (no auto-detect):

```bash
cd infra/conductor
docker compose up                                            # CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up   # GPU
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
cdt library "bounded context"
```

## GPU (auto-detected)

CPU embedding of the full corpus takes **hours**. `cdt up`
detects an NVIDIA GPU + the NVIDIA Container Toolkit and enables the GPU
automatically (~0.5 s/embed, like local dev). The `conductor` service then
**confirms the real mode** after the pull — it warms bge-m3 and reports
`bge-m3 on GPU (… VRAM)` or `bge-m3 on CPU`. If you have a GPU but it reports
CPU, install the NVIDIA Container Toolkit and re-run.

## Notes

- `to-brain.7z` is gitignored (it is the corpus, not source). Zip the **category
  folders** (e.g. `08_sistemas_distribuidos/…`) at the archive root so the
  ingest keeps the right `category` metadata.
- Port 8001 is used for Chroma so it does not clash with Honcho on 8000
  (`infra/honcho/`).
- This stack is independent from the Honcho diary stack; run either or both.
