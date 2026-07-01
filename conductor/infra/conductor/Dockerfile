# The `conductor` bootstrap image: fetches the books (from the library repo) and
# ingests them into ChromaDB via bge-m3. It installs Conductor straight from the
# public repo with pip's git+https support — so the build context is just this
# folder (which ships inside the pip/uv package) and `cdt up` needs NO source
# clone on the host, no registry, no credentials.
#
# Pin CONDUCTOR_REF to the installed tag (compose passes it as a build arg) to
# keep the image in lock-step with the CLI; default is the repo's main branch.
FROM python:3.13-slim

ARG CONDUCTOR_REPO=https://github.com/eltonssouza/conductor-main.git
ARG CONDUCTOR_REF=main

# Conductor + the rag extra (chromadb). py7zr stays for the optional offline
# .7z seed (CONDUCTOR_LIBRARY_ARCHIVE); the default repo fetch is pure stdlib.
# git is needed only to resolve the git+https install spec — install it, use it,
# then purge it so it never ships in the runtime image (bootstrap fetches the
# corpus over plain https, no git at run time).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir "conductor[rag] @ git+${CONDUCTOR_REPO}@${CONDUCTOR_REF}" py7zr \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

ENV CONDUCTOR_LIBRARY=/data/library
ENTRYPOINT ["python", "-m", "conductor.rag.bootstrap"]
