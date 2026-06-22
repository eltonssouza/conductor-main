#!/usr/bin/env python3
"""`python -m rag.bootstrap` — one-shot RAG stack setup with visible progress.

Run as the `conductor` service in infra/conductor/. It brings the library RAG
online end to end and prints the progress of each step:

  [1/4] fetch the books from the library repo into the library
  [2/4] pull the bge-m3 model in Ollama   (streamed % progress)
  [3/4] wait for ChromaDB to be ready
  [4/4] ingest the books into ChromaDB    (rag.ingest progress)

Idempotent: the fetch skips a populated library, the pull skips an existing
model, and the ingest upserts — so re-running resumes instead of duplicating.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

LIBRARY = Path(os.environ.get("CONDUCTOR_LIBRARY", "/data/library"))
# Corpus source: a public GitHub repo of reference books, fetched as a tarball
# (stdlib urllib + tarfile — no git, no py7zr). `CONDUCTOR_LIBRARY_ARCHIVE` is an
# optional offline override (a local .7z) that wins when it points to a real file.
LIBRARY_REPO = os.environ.get("CONDUCTOR_LIBRARY_REPO", "eltonssouza/conductor-library")
LIBRARY_REF = os.environ.get("CONDUCTOR_LIBRARY_REF", "main")
ARCHIVE = (Path(os.environ["CONDUCTOR_LIBRARY_ARCHIVE"])
           if os.environ.get("CONDUCTOR_LIBRARY_ARCHIVE") else None)
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

_SEL_MARKER = ".selection"


def _selection_key() -> str:
    """A stable fingerprint of the current tier/stack selection, so a re-run only
    re-fetches when the selection changed (else the populated library is kept)."""
    from .core import LIBRARY_TIERS, LIBRARY_STACKS
    return f"tiers={','.join(LIBRARY_TIERS)};stacks={','.join(LIBRARY_STACKS)}"


def step_extract() -> None:
    key = _selection_key()
    marker = LIBRARY / _SEL_MARKER
    populated = any(LIBRARY.rglob("*.md"))
    if populated and marker.is_file() and marker.read_text(encoding="utf-8").strip() == key:
        log("1/4", f"library already populated for this selection; skipping fetch")
        return
    if ARCHIVE and ARCHIVE.is_file():
        _extract_archive()        # offline 7z: extracts all; the ingest filters
    else:
        _fetch_repo_corpus()      # repo fetch: extracts only the selected books
    try:
        LIBRARY.mkdir(parents=True, exist_ok=True)
        marker.write_text(key + "\n", encoding="utf-8")
    except OSError:
        pass


def _extract_archive() -> None:
    """Offline override: extract books from a local .7z (CONDUCTOR_LIBRARY_ARCHIVE)."""
    import py7zr
    LIBRARY.mkdir(parents=True, exist_ok=True)
    log("1/4", f"extracting {ARCHIVE.name} -> {LIBRARY}")
    with py7zr.SevenZipFile(ARCHIVE, mode="r") as z:
        names = z.getnames()
        z.extractall(path=LIBRARY)
    md = sum(1 for _ in LIBRARY.rglob("*.md"))
    log("1/4", f"extracted {len(names)} entries ({md} .md books)")


def _fetch_repo_corpus() -> None:
    """Default: download the library repo's tarball and extract the **selected**
    `.md` books (by `software_dev` tier + language/framework `stack`).

    Only the books the developer needs are written to disk (and thus chunked and
    embedded) — e.g. a Java+Angular dev gets `core` + `stack: java` + `stack:
    angular`, not the Ruby/Go/React books. Keeps each book's category folder so
    category detection works; repo-root meta files are skipped. Network failure
    leaves the library empty (the ingest then no-ops) instead of crashing.
    """
    from .core import split_frontmatter, select_corpus, LIBRARY_TIERS, LIBRARY_STACKS
    url = f"https://github.com/{LIBRARY_REPO}/archive/refs/heads/{LIBRARY_REF}.tar.gz"
    log("1/4", f"fetching library from {LIBRARY_REPO}@{LIBRARY_REF} "
               f"(tiers={','.join(LIBRARY_TIERS)}; stacks={','.join(LIBRARY_STACKS) or 'none'})")
    LIBRARY.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=180) as resp:
            blob = resp.read()
    except Exception as e:  # noqa: BLE001 — network/HTTP errors must not crash the stack
        log("1/4", f"WARNING: could not fetch {url}: {e} (library left empty)")
        return
    root = str(LIBRARY.resolve())
    # Read every .md member once, keyed by its on-disk relative path; selection
    # (incl. nearest-version stack resolution) needs to see all editions first.
    payload: dict = {}   # rel -> bytes
    metas: dict = {}     # rel -> frontmatter
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or not m.name.endswith(".md"):
                continue
            _, _, rel = m.name.partition("/")      # strip "<repo>-<ref>/"
            if not rel or "/" not in rel:           # skip repo-root meta docs
                continue
            if not str((LIBRARY / rel).resolve()).startswith(root):  # path-traversal guard
                continue
            src = tf.extractfile(m)
            if src is None:
                continue
            data = src.read()
            payload[rel] = data
            metas[rel], _ = split_frontmatter(data.decode("utf-8", "replace"))
    selected = select_corpus(metas, LIBRARY_TIERS, LIBRARY_STACKS)
    for rel in selected:
        dest = LIBRARY / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload[rel])
    log("1/4", f"fetched {len(selected)} selected .md book(s) into {LIBRARY} "
               f"({len(payload) - len(selected)} skipped by selection)")


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
    _gpu_report()


def _gpu_report() -> None:
    """Warms the model and reports whether it actually runs on GPU or CPU."""
    try:
        warm = json.dumps({"model": MODEL, "input": "warmup"}).encode("utf-8")
        urllib.request.urlopen(urllib.request.Request(
            f"{OLLAMA}/api/embed", data=warm,
            headers={"Content-Type": "application/json"}), timeout=180)
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
            models = json.loads(r.read().decode("utf-8")).get("models", [])
        for m in models:
            if MODEL in m.get("name", ""):
                vram = m.get("size_vram", 0) or 0
                if vram > 0:
                    log("2/4", f"bge-m3 on GPU ({vram / 1e9:.1f} GB VRAM) — fast embeds")
                else:
                    log("2/4", "bge-m3 on CPU — ingest will be slow (hours). "
                               "For GPU, launch via `python -m rag.stack up`.")
                return
    except Exception:
        pass  # reporting only; never block the build


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
