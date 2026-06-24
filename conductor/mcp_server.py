#!/usr/bin/env python3
"""`cdt mcp` — expose Conductor's two memories as an MCP stdio server.

Any MCP-capable AI harness can call Conductor's library RAG and per-project
diary natively as tools, instead of shelling out to `cdt library` / `cdt
journal`. The teammate-owned connector scaffolding registers THIS server
(command `cdt`, args `["mcp"]`), so this module only has to launch a working
stdio server over the official MCP Python SDK.

The `mcp` package is an optional extra: importing this module must always
succeed (CI imports it), so the SDK is imported lazily inside `main()` — exactly
like `chromadb` / `honcho-ai` are handled elsewhere. Without the extra, `main()`
prints an actionable hint to stderr and returns 1.

Tools exposed:
  - library_search(question)            -> RAG passages from the reference books
  - journal_recall(question)            -> semantic recall from this project's diary
  - journal_add(gate, kind, text)       -> append a diary entry, return confirmation
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from .project import find_project_root, force_utf8, read_config

# Valid diary entry kinds (mirror of journal.KINDS, minus the internal
# "checkpoint"/"observation" kinds that are not for manual use).
_KINDS = ("reasoning", "decision", "plan", "error", "solution")


def _tool_library_search(question: str) -> str:
    """RAG over the reference books; never raises (returns an explanatory string)."""
    question = (question or "").strip()
    if not question:
        return "Provide a non-empty question to search the library."
    try:
        from .library import search
        from .rag.core import BackendUnreachable
    except ImportError:
        return ("Library search needs the optional RAG extra: "
                "pip install 'conductor[rag]' (and a running stack: cdt up).")
    try:
        hits = search(question, k=5)
    except BackendUnreachable as e:
        return f"Library backend unreachable: {e}"
    except Exception as e:  # noqa: BLE001 — missing/empty index, malformed query
        return (f"Library search failed: {e}. "
                "Hint: run `cdt up`, then `cdt library reindex`.")
    if not hits:
        return "No passages found in the library for that question."
    lines: List[str] = []
    for i, h in enumerate(hits, 1):
        loc = h["source"] + (f" — {h['section']}" if h.get("section") else "")
        snippet = (h.get("text") or "").strip().replace("\n", " ")
        lines.append(f"#{i} [{h['score']:.3f}] {loc} ({h.get('path', '')})\n{snippet}")
    return "\n\n".join(lines)


def _tool_journal_recall(question: str) -> str:
    """Semantic recall from the current project's diary; never raises."""
    question = (question or "").strip()
    if not question:
        return "Provide a non-empty question to recall from the diary."
    root = find_project_root()
    config = read_config(root)
    if config is None:
        return (f"Not an enrolled project (no .cdt/ at {root}). "
                "Run `cdt init` here first.")
    try:
        from .honcho_client import HonchoBackend
        from .journal import _session_id
    except ImportError:
        return ("Journal recall needs the optional Honcho extra: "
                "pip install 'conductor[honcho]'.")
    try:
        backend = HonchoBackend.from_config(config)
        res = backend.recall(_session_id(config, None), question)
    except Exception as e:  # noqa: BLE001 — backend unreachable / unexpected error
        return f"Journal recall failed: {e}"
    if res.ok and res.text:
        return res.text
    return ("No diary recall available "
            f"({res.detail or 'Honcho returned nothing'}).")


def _tool_journal_add(gate: int, kind: str, text: str) -> str:
    """Append a diary entry to the local mirror (and best-effort Honcho); never raises."""
    text = (text or "").strip()
    if not text:
        return "Provide non-empty text for the diary entry."
    if kind not in _KINDS:
        return f"Unknown kind '{kind}'; choose from {', '.join(_KINDS)}."
    root = find_project_root()
    config = read_config(root)
    if config is None:
        return (f"Not an enrolled project (no .cdt/ at {root}). "
                "Run `cdt init` here first.")
    try:
        from .honcho_client import HonchoBackend
        from .journal import _mirror_path, _session_id, _write_mirror
    except ImportError:
        return ("Journal add needs the optional Honcho extra: "
                "pip install 'conductor[honcho]'.")
    try:
        session_id = _session_id(config, None)
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "session": session_id,
            "author": "conductor",
            "kind": kind,
            "gate": gate,
            "text": text,
        }
        mirror = _mirror_path(root, session_id)
        _write_mirror(mirror, entry)
        backend = HonchoBackend.from_config(config)
        res = backend.add(session_id, text, gate=gate, kind=kind, as_owner=False)
    except Exception as e:  # noqa: BLE001 — never kill the server on a bad add
        return f"Journal add failed: {e}"
    synced = "synced to Honcho" if res.ok else f"mirrored locally only ({res.detail})"
    return f"Logged [{kind}/gate {gate}] to {mirror.name}; {synced}."


def main(argv: Optional[List[str]] = None) -> int:
    """Build the FastMCP server and run it over stdio (default transport)."""
    force_utf8()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        import sys
        print("MCP server needs the optional extra: "
              "pip install 'conductor[mcp]'", file=sys.stderr)
        return 1

    server = FastMCP("conductor")

    @server.tool()
    def library_search(question: str) -> str:
        """Search the Conductor library (RAG over reference books) for passages
        relevant to a question. Returns the top matching passages as text."""
        return _tool_library_search(question)

    @server.tool()
    def journal_recall(question: str) -> str:
        """Recall past context from the current project's development diary by
        meaning. Returns what the diary remembers about the question."""
        return _tool_journal_recall(question)

    @server.tool()
    def journal_add(gate: int, kind: str, text: str) -> str:
        """Append an entry to the current project's development diary.
        kind is one of: reasoning, decision, plan, error, solution.
        gate is the flow gate number (1-11). Returns a confirmation."""
        return _tool_journal_add(gate, kind, text)

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
