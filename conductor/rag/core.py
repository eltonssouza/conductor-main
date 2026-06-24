"""Core of the Conductor RAG.

Pipeline: library markdown → chunks → bge-m3 embeddings (via Ollama) →
persistent ChromaDB. Shared by the `ingest.py` and `query.py` CLIs.

Runtime dependencies (owner decision, 2026-06-14):
- Ollama serving `bge-m3` at http://localhost:11434 (1024-d embeddings).
- chromadb as the vector store.

Ollama access uses only urllib (stdlib); only ChromaDB is third-party.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


class BackendUnreachable(RuntimeError):
    """A RAG backend (Ollama embeddings or ChromaDB) could not be reached.

    Carries a self-contained, actionable message (names the URL and the fix) so
    callers can print it straight to stderr instead of an opaque urllib/Chroma
    traceback. Raised by `embed()` and the Chroma client helpers.
    """


def force_utf8() -> None:
    """Ensures stdout/stderr use UTF-8 (Windows console defaults to cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

# --- configuration -----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
# Host-side library dir, used only by `cdt library add|reindex` (search hits
# ChromaDB over HTTP, not the disk). Defaults to a per-user cache; the Docker
# stack fetches its own copy from the library repo into a container volume.
LIBRARY_DIR = Path(os.environ.get(
    "CONDUCTOR_LIBRARY", str(Path.home() / ".conductor" / "library")))
CHROMA_DIR = Path(os.environ.get("CONDUCTOR_CHROMA", str(REPO_ROOT / "rag" / "chroma")))


def _csv_env(name: str) -> List[str]:
    return [s.strip().lower() for s in os.environ.get(name, "").split(",") if s.strip()]


# Corpus selection — what gets ingested (the rest is fetched but skipped):
#  - TIERS: `software_dev` frontmatter tiers to include (default: core only).
#  - STACKS: language/framework `stack:` tags to include. Empty = stack-less,
#    language-agnostic books only (the default). "all" includes every stack.
# So out of the box the index is "core, language-agnostic"; a user opts into the
# languages/frameworks they use via CONDUCTOR_LIBRARY_STACKS=python,angular,...
LIBRARY_TIERS = _csv_env("CONDUCTOR_LIBRARY_TIERS") or ["core"]
LIBRARY_STACKS = _csv_env("CONDUCTOR_LIBRARY_STACKS")
# Resident Chroma server ("host:port"). Defaults to the dockerized stack
# (`cdt up` exposes ChromaDB on localhost:8001), so `cdt library`
# works with no env setup. The in-container bootstrap overrides this with
# `chroma:8000`. Set to empty to use a local persistent index instead.
CHROMA_HTTP = os.environ.get("CONDUCTOR_CHROMA_HTTP", "localhost:8001").strip()
COLLECTION = "library"

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.environ.get("CONDUCTOR_EMBED_MODEL", "bge-m3")
EMBED_DIM = 1024
# Keep bge-m3 resident in Ollama between calls so agent queries skip the model
# cold-start. "-1" = never unload; e.g. "30m" for a TTL. Configurable.
EMBED_KEEP_ALIVE = os.environ.get("CONDUCTOR_KEEP_ALIVE", "30m")

# Chunking: target in characters (~512 tokens) with 1-paragraph overlap.
CHUNK_TARGET_CHARS = 1500
CHUNK_MAX_CHARS = 2400
EMBED_BATCH = 64
# Safety cap per text sent to Ollama (bge-m3 ~8192 tokens). Above this,
# /api/embed returns HTTP 400; we truncate to never overflow.
EMBED_CHAR_CAP = 6000

# HNSW index tuning for the vector store. Higher M / construction_ef = better
# recall and denser graph (slower build, more RAM); search_ef trades query
# latency for recall. Sized for a ~60k-chunk corpus queried by agents.
HNSW_CONFIG = {
    "hnsw:space": "cosine",
    "hnsw:M": int(os.environ.get("CONDUCTOR_HNSW_M", "32")),
    "hnsw:construction_ef": int(os.environ.get("CONDUCTOR_HNSW_CONSTRUCTION_EF", "200")),
    "hnsw:search_ef": int(os.environ.get("CONDUCTOR_HNSW_SEARCH_EF", "128")),
}


# --- chunking ----------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str       # file name (book)
    category: str     # top-level directory
    section: str      # last markdown heading seen
    path: str         # path relative to the library


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
# Control chars except tab/newline/carriage-return. NUL bytes (UTF-16 leftovers
# in some corpus files) make Ollama /api/embed return HTTP 400, so we strip them.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize(text: str) -> str:
    """Removes NUL and other C0 control chars that break the embeddings API."""
    return _CTRL_RE.sub("", text)


def chunk_markdown(text: str, *, source: str, category: str, path: str) -> List[Chunk]:
    """Splits markdown into chunks by paragraphs, packing up to ~target chars.

    Tracks the last heading as `section` to provide context for each chunk.
    """
    chunks: List[Chunk] = []
    section = ""
    buf: List[str] = []
    buf_len = 0
    idx = 0

    def flush():
        nonlocal buf, buf_len, idx
        if not buf:
            return
        body = sanitize("\n\n".join(buf).strip())
        if body:
            chunks.append(Chunk(
                chunk_id=f"{path}::{idx}",
                text=(f"[{source} — {section}]\n{body}" if section else f"[{source}]\n{body}"),
                source=source, category=category, section=section, path=path,
            ))
            idx += 1
        buf, buf_len = [], 0

    # paragraphs separated by blank lines; oversized paragraphs (tables,
    # code blocks without blank lines) are sliced to avoid overflowing the
    # embedding model's context.
    raw_paras = re.split(r"\n\s*\n", text)
    paras: List[str] = []
    for p in raw_paras:
        p = p.strip()
        if not p:
            continue
        if len(p) > CHUNK_MAX_CHARS:
            paras.extend(p[i:i + CHUNK_MAX_CHARS] for i in range(0, len(p), CHUNK_MAX_CHARS))
        else:
            paras.append(p)

    for para in paras:
        m = _HEADING_RE.match(para.splitlines()[0])
        if m:
            section = m.group(1).strip()[:120]
        plen = len(para)
        if buf_len + plen > CHUNK_TARGET_CHARS and buf:
            tail = buf[-1] if buf_len + plen <= CHUNK_MAX_CHARS else None
            flush()
            if tail and len(tail) < CHUNK_TARGET_CHARS // 2:
                buf, buf_len = [tail], len(tail)  # light overlap
        buf.append(para)
        buf_len += plen
        if buf_len >= CHUNK_MAX_CHARS:
            flush()
    flush()
    return chunks


def split_frontmatter(text: str):
    """Returns ({key: value}, body) for a leading `--- key: value --- ` block.

    Flat `key: value` lines only (the corpus convention: `software_dev`, `stack`).
    Returns ({}, text) when there is no frontmatter.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].strip("\n").splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip().lower()
    body = text[end + 4:].lstrip("\n")
    return meta, body


def is_selected(meta: dict, tiers: List[str], stacks: List[str]) -> bool:
    """Whether a file's frontmatter passes the current corpus selection.

    A `stack:` field marks a language/framework-specific book (the corpus tags
    these `software_dev: stack`); it is **opt-in** — included only when its stack
    is chosen (or "all"), regardless of tier. Everything else is selected by its
    `software_dev` tier (default: core). A missing tier defaults to `core`.
    """
    stack = meta.get("stack", "")
    if stack:
        return "all" in stacks or stack in stacks
    tier = meta.get("software_dev", "core") or "core"
    return tier in tiers


def _parse_stacks(stacks: List[str]):
    """`['java@25', 'angular', 'all']` -> ({'java': 25, 'angular': None}, want_all)."""
    req: dict = {}
    want_all = False
    for s in stacks:
        s = s.strip().lower()
        if not s:
            continue
        if s == "all":
            want_all = True
            continue
        sid, _, ver = s.partition("@")
        req[sid] = int(ver) if ver.isdigit() else None
    return req, want_all


def _book_version(meta: dict):
    v = meta.get("version")
    try:
        return int(str(v).split(".")[0]) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def select_corpus(metas: "dict[str, dict]", tiers: List[str], stacks: List[str]) -> set:
    """Pick the corpus keys to ingest from {key: frontmatter}.

    Tier (non-`stack`) books are chosen by `software_dev` tier. `stack` books are
    opt-in: a requested `stack@<version>` resolves to the **nearest** book version
    (closest major; ties prefer the higher), while a bare `stack` (or `all`) takes
    every edition. Unversioned editions of a requested stack are always included.
    """
    req, want_all = _parse_stacks(stacks)
    groups: dict = {}     # stack_id -> list[(version|None, key)]
    chosen: set = set()
    for key, meta in metas.items():
        stack = (meta.get("stack") or "").strip().lower()
        if stack:
            groups.setdefault(stack, []).append((_book_version(meta), key))
        else:
            tier = (meta.get("software_dev") or "core").strip().lower()
            if tier in tiers:
                chosen.add(key)
    for sid, editions in groups.items():
        if not (want_all or sid in req):
            continue
        target = None if want_all else req.get(sid)
        versioned = [(v, k) for v, k in editions if v is not None]
        chosen.update(k for v, k in editions if v is None)   # unversioned: always in
        if target is None or not versioned:
            chosen.update(k for _, k in versioned)            # take every edition
        else:                                                 # nearest major (tie -> higher)
            best = min(abs(v - target) for v, _ in versioned)
            near = sorted((v for v, _ in versioned if abs(v - target) == best), reverse=True)[0]
            chosen.update(k for v, k in versioned if v == near)
    return chosen


def discover_stacks(repo: Optional[str] = None, ref: Optional[str] = None) -> "dict[str, dict]":
    """Read the library's generated catalog and list its opt-in stacks.

    Returns `{stack_id: {"versions": [majors...], "category": "<NN_folder>"}}` from
    `LIBRARY_INDEX.json` — the authoritative, machine-readable catalog the library
    repo generates from frontmatter (see its FILE_CONVENTIONS.md §7). One small
    fetch instead of downloading and decoding the whole tarball. Network/parse
    failure -> {} (caller handles).
    """
    import json
    import urllib.request

    repo = repo or os.environ.get("CONDUCTOR_LIBRARY_REPO", "eltonssouza/conductor-library")
    ref = ref or os.environ.get("CONDUCTOR_LIBRARY_REF", "main")
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/LIBRARY_INDEX.json"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            idx = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 — caller reports "couldn't reach the repo"
        return {}
    out: dict = {}
    for sid, s in (idx.get("stacks") or {}).items():
        editions = s.get("editions") or []
        category = editions[0]["path"].split("/")[0] if editions else ""
        out[sid] = {
            "versions": [str(v) for v in (s.get("versions") or [])],
            "category": category,
        }
    return dict(sorted(out.items()))


def iter_corpus(library: Path = LIBRARY_DIR, *, tiers: Optional[List[str]] = None,
                stacks: Optional[List[str]] = None) -> Iterable[Chunk]:
    """Walks `library/**/*.md` and yields chunks for the *selected* books.

    Selection (tiers + language/framework stacks) defaults to the env-configured
    `LIBRARY_TIERS` / `LIBRARY_STACKS`. The frontmatter block is stripped before
    chunking so the `software_dev`/`stack` tags are not embedded.
    """
    tiers = tiers if tiers is not None else LIBRARY_TIERS
    stacks = stacks if stacks is not None else LIBRARY_STACKS
    files = {str(md.relative_to(library)): md for md in sorted(library.rglob("*.md"))}
    # Pass 1: read just the frontmatter head (cheap) to decide selection — nearest
    # version matching needs to see every edition before picking.
    metas = {}
    for key, md in files.items():
        try:
            head = md.open(encoding="utf-8", errors="replace").read(4096)
        except OSError:
            continue
        metas[key], _ = split_frontmatter(head)
    selected = select_corpus(metas, tiers, stacks)
    # Pass 2: chunk only the selected books (frontmatter stripped from the body).
    for key in sorted(selected):
        md = files[key]
        rel = md.relative_to(library)
        category = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        _, body = split_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        yield from chunk_markdown(
            body, source=md.stem, category=category, path=str(rel).replace("\\", "/"),
        )


# --- embeddings (Ollama bge-m3) ---------------------------------------------

def embed(texts: List[str]) -> List[List[float]]:
    """Embeds a list of texts via Ollama /api/embed (batch). 1024-d.

    Each text is truncated to EMBED_CHAR_CAP and empty strings become a space,
    so Ollama never returns HTTP 400. Inputs are already sanitized at chunk
    creation (chunk_markdown), so we only truncate here.
    """
    safe = [(t[:EMBED_CHAR_CAP] or " ") for t in texts]
    payload = json.dumps({"model": EMBED_MODEL, "input": safe,
                          "keep_alive": EMBED_KEEP_ALIVE}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError:
        # Ollama answered with an error status (e.g. 400/404) — it IS reachable;
        # this is a real model/payload problem, so let it surface as-is.
        raise
    except urllib.error.URLError as e:  # connection refused, DNS, timeout
        raise BackendUnreachable(
            f"Embedding backend (Ollama) unreachable at {OLLAMA_URL}. "
            f"Is the stack up? Try: cdt up  (reason: {e.reason})"
        ) from e
    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise RuntimeError(f"Ollama returned {len(embs or [])} embeddings for {len(texts)} texts")
    return embs


# --- ChromaDB ----------------------------------------------------------------

def _chroma_down(e: Exception) -> "BackendUnreachable":
    """Builds the actionable 'backend unreachable' error for a Chroma failure."""
    where = f"http://{CHROMA_HTTP}" if CHROMA_HTTP else str(CHROMA_DIR)
    return BackendUnreachable(
        f"Library backend (ChromaDB) unreachable at {where}. "
        f"Is the stack up? Try: cdt up  ({e})"
    )


def _client():
    """Chroma client: resident HTTP server if CONDUCTOR_CHROMA_HTTP is set,
    otherwise the local persistent client. A connection failure to the HTTP
    server is reported as BackendUnreachable (named URL + fix), not a raw
    Chroma/connection traceback."""
    import chromadb  # late import: heavy dependency

    if CHROMA_HTTP:
        host, _, port = CHROMA_HTTP.partition(":")
        try:
            return chromadb.HttpClient(host=host or "localhost", port=int(port or "8000"))
        except Exception as e:  # noqa: BLE001 — server down / connection refused
            raise _chroma_down(e) from e
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(create: bool = True):
    """Opens (or creates) the library collection.

    On create, applies the tuned HNSW_CONFIG; falls back to cosine-only if the
    installed chromadb rejects the extra keys. A connection failure to a resident
    Chroma server raises BackendUnreachable with an actionable message; a genuinely
    missing collection (server up, never ingested) is left to propagate as-is.
    """
    client = _client()
    if not create:
        try:
            return client.get_collection(COLLECTION)
        except BackendUnreachable:
            raise
        except Exception as e:  # noqa: BLE001
            # Distinguish "server unreachable" from "collection does not exist":
            # a connection error means the backend is down; anything else (e.g.
            # the collection was never created) is a real, different problem.
            if _is_connection_error(e):
                raise _chroma_down(e) from e
            raise
    try:
        return client.get_or_create_collection(COLLECTION, metadata=dict(HNSW_CONFIG))
    except Exception:  # noqa: BLE001 — older/newer chromadb metadata schema
        try:
            return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        except Exception as e:  # noqa: BLE001 — server unreachable on create
            if _is_connection_error(e):
                raise _chroma_down(e) from e
            raise


def _is_connection_error(e: Exception) -> bool:
    """Heuristic: does this Chroma exception indicate the server is unreachable
    (vs. a missing collection or a schema error)? Chroma wraps httpx/requests
    connection failures in its own types, so we match on type name + message
    rather than importing those optional libraries."""
    name = type(e).__name__.lower()
    if "connect" in name or name in ("connecterror", "connectionerror"):
        return True
    msg = str(e).lower()
    return any(s in msg for s in (
        "connection refused", "failed to connect", "max retries",
        "connection error", "could not connect", "[errno 111]", "[errno 61]",
        "connection aborted", "name or service not known", "timed out",
    ))
