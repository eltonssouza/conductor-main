#!/usr/bin/env python3
"""`python -m rag.bootstrap` — one-shot RAG stack setup with visible progress.

Run as the `conductor` service in infra/conductor/. It brings the library RAG
online end to end and prints the progress of each step:

  [1/4] extract the books from to-brain.7z into the library
  [2/4] pull the bge-m3 model in Ollama   (streamed % progress)
  [3/4] wait for ChromaDB to be ready
  [4/4] ingest the books into ChromaDB    (rag.ingest progress)

Idempotent: extraction skips a populated library, the pull skips an existing
model, and the ingest upserts — so re-running resumes instead of duplicating.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LIBRARY = Path(os.environ.get("CONDUCTOR_LIBRARY", "/data/library"))
ARCHIVE = Path(os.environ.get("CONDUCTOR_LIBRARY_ARCHIVE", "/seed/to-brain.7z"))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://ollama:11434").rstrip("/")
MODEL = os.environ.get("CONDUCTOR_EMBED_MODEL", "bge-m3")
CHROMA_HTTP = os.environ.get("CONDUCTOR_CHROMA_HTTP", "chroma:8000")


def log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}", flush=True)


def _wait(urls, name: str, step: str, timeout: int = 600) -> bool:
    """Polls a list of candidate URLs until one answers (or timeout)."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        for url in urls:
            try:
                urllib.request.urlopen(url, timeout=5)
                log(step, f"{name} is up")
                return True
            except urllib.error.HTTPError:
                log(step, f"{name} is up")   # any HTTP response = reachable
                return True
            except Exception:
                pass
        time.sleep(2)
    log(step, f"WARNING: {name} not reachable after {timeout}s")
    return False


# --- [1/4] extract books -----------------------------------------------------

def step_extract() -> None:
    if any(LIBRARY.rglob("*.md")):
        log("1/4", f"library already populated at {LIBRARY}; skipping extraction")
        return
    if not ARCHIVE.is_file():
        log("1/4", f"no archive at {ARCHIVE}; skipping (mount to-brain.7z to seed books)")
        return
    import py7zr
    LIBRARY.mkdir(parents=True, exist_ok=True)
    log("1/4", f"extracting {ARCHIVE.name} -> {LIBRARY}")
    with py7zr.SevenZipFile(ARCHIVE, mode="r") as z:
        names = z.getnames()
        z.extractall(path=LIBRARY)
    md = sum(1 for _ in LIBRARY.rglob("*.md"))
    log("1/4", f"extracted {len(names)} entries ({md} .md books)")


# --- [2/4] pull bge-m3 -------------------------------------------------------

def _model_present() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
            tags = json.loads(r.read().decode("utf-8")).get("models", [])
        return any(MODEL in m.get("name", "") for m in tags)
    except Exception:
        return False


def step_pull() -> None:
    _wait([f"{OLLAMA}/api/tags"], "Ollama", "2/4")
    if _model_present():
        log("2/4", f"{MODEL} already pulled; skipping")
        return
    log("2/4", f"pulling {MODEL} (first run downloads ~1.2 GB)")
    payload = json.dumps({"model": MODEL, "stream": True}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA}/api/pull", data=payload,
                                 headers={"Content-Type": "application/json"})
    last = ""
    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            d = json.loads(line)
            status = d.get("status", "")
            total, done = d.get("total"), d.get("completed")
            if total and done is not None:
                pct = 100.0 * done / total
                print(f"\r[2/4] {status}: {pct:5.1f}%   ", end="", flush=True)
            elif status != last:
                print(f"\r[2/4] {status}{' ' * 30}", end="", flush=True)
                last = status
    print()
    log("2/4", f"{MODEL} ready")


# --- [3/4] chroma ------------------------------------------------------------

def step_chroma() -> None:
    host, _, port = CHROMA_HTTP.partition(":")
    port = port or "8000"
    _wait([f"http://{host}:{port}/api/v2/heartbeat",
           f"http://{host}:{port}/api/v1/heartbeat"], "ChromaDB", "3/4")


# --- [4/4] ingest ------------------------------------------------------------

def step_ingest() -> int:
    log("4/4", f"ingesting books from {LIBRARY} into ChromaDB ({CHROMA_HTTP})")
    from .ingest import main as ingest_main
    return ingest_main([])


def main() -> int:
    log("0/4", "Conductor RAG bootstrap starting")
    step_extract()
    step_pull()
    step_chroma()
    rc = step_ingest()
    log("done", "RAG stack ready" if rc == 0 else f"ingest exited with {rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
