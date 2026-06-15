# The `conductor` bootstrap image: extracts the books and ingests them into
# ChromaDB via bge-m3. Built from the local source (build context = repo root),
# so `conductor up` works from a repo clone without any registry/credentials.
FROM python:3.13-slim

WORKDIR /app
COPY . /app

# Conductor + the rag extra (chromadb) + py7zr for the to-brain.7z extraction.
RUN pip install --no-cache-dir .[rag] py7zr

ENV CONDUCTOR_LIBRARY=/data/library
ENTRYPOINT ["python", "-m", "conductor.rag.bootstrap"]
