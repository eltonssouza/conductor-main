# Conductor MCP server (Docker)

A networked MCP server that exposes Conductor's two memories as tools, so any
MCP-capable harness reachable over the network — e.g. an Odysseus install running
in Docker — can call them by URL instead of spawning `cdt mcp` as a stdio
subprocess.

**Tools:** `library_search` (RAG over the reference books), `journal_recall`,
`journal_add` (the per-project development diary).

**Transport:** streamable-http. Endpoint: `http://<host>:8808/mcp`.

## Run

```bash
cd infra/mcp
docker compose up -d --build
```

Server-only: it reaches its backends over the network. For `library_search`,
start the RAG stack first so ChromaDB + Ollama are up:

```bash
cdt up          # exposes ChromaDB on localhost:8001 and Ollama on 11434
```

Override backend locations via env (or an `.env` next to the compose file):

| Env | Default | Purpose |
|-----|---------|---------|
| `MCP_PORT` | `8808` | host port for the endpoint |
| `MCP_BIND` | `127.0.0.1` | host bind address |
| `CONDUCTOR_CHROMA_HTTP` | `host.docker.internal:8001` | ChromaDB host:port |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | embeddings server |
| `CONDUCTOR_LIBRARY_STACKS` | _(empty)_ | extra library stacks to query |

If a backend is down, that tool returns an explanatory string (it never crashes
the server).

### journal tools (optional)

`journal_recall` / `journal_add` operate on the *current project*. To enable
them, uncomment the `volumes:` + `working_dir:` lines in `docker-compose.yml`,
set `CONDUCTOR_PROJECT` to an enrolled project (one with a `.cdt/`), and make
sure that project's `honcho.base_url` is reachable from the container (e.g.
`http://host.docker.internal:8000`). Without a mounted project, `library_search`
still works and the journal tools reply "not an enrolled project".

## Connect a harness

Point an MCP client at the streamable-http endpoint:

- From the host: `http://localhost:8808/mcp`
- From another container (e.g. Odysseus): `http://host.docker.internal:8808/mcp`

For Odysseus specifically, register it as an `http` MCP server (Settings → MCP
Servers, or `cdt odysseus install --with-mcp` seeds the row for you).
