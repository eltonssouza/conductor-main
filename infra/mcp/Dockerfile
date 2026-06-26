# Conductor MCP server — exposes the library (RAG) + journal memories over MCP
# so any networked, MCP-capable harness (e.g. an Odysseus install in Docker) can
# call them by URL. Server-only: the RAG/diary backends live elsewhere and are
# reached over the network (see docker-compose.yml env).
#
# Build context is the repository root (see docker-compose.yml: context: ../..).
FROM python:3.12-slim

WORKDIR /app
COPY . /app

# [mcp] = the MCP SDK; [rag] = ChromaDB client for library_search; [honcho] = the
# diary client for journal_recall/journal_add. Embeddings (Ollama) and the Chroma
# server are reached over the network, not installed here.
RUN pip install --no-cache-dir ".[mcp,rag,honcho]"

# Networked transport defaults; override at runtime if needed.
ENV CONDUCTOR_CHROMA_HTTP=host.docker.internal:8001 \
    OLLAMA_HOST=http://host.docker.internal:11434

EXPOSE 8808

# streamable-http serves the MCP endpoint at /mcp on 0.0.0.0:8808.
ENTRYPOINT ["cdt", "mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8808"]
