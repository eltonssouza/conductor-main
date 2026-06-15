# The `conductor` bootstrap image: extracts the books and ingests them into
# ChromaDB via bge-m3. Build context is the repo root.
FROM python:3.13-slim

WORKDIR /app
COPY . /app

# rag extra (chromadb) + py7zr for the to-brain.7z extraction.
RUN pip install --no-cache-dir -e .[rag] py7zr

ENV CONDUCTOR_LIBRARY=/data/library
ENTRYPOINT ["python", "-m", "rag.bootstrap"]
