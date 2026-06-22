# The `conductor` bootstrap image: fetches the books (from the library repo) and
# ingests them into ChromaDB via bge-m3. Built from the local source (build
# context = repo root), so `conductor up` works from a repo clone without any
# registry/credentials.
FROM python:3.13-slim

WORKDIR /app
COPY . /app

# Conductor + the rag extra (chromadb). py7zr stays for the optional offline
# .7z seed (CONDUCTOR_LIBRARY_ARCHIVE); the default repo fetch is pure stdlib.
RUN pip install --no-cache-dir .[rag] py7zr

ENV CONDUCTOR_LIBRARY=/data/library
ENTRYPOINT ["python", "-m", "conductor.rag.bootstrap"]
