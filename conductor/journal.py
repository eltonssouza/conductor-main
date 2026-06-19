#!/usr/bin/env python3
"""`python -m cdt.journal` — the per-project development diary.

Records the reasoning/decisions/plans/errors/solutions of each gate and recalls
them later. Every entry is written to a **local JSONL mirror** first (the source
of truth, works offline), then best-effort synced to Honcho for background
reasoning and meaning-based recall.

  python -m cdt.journal add --gate 4 --kind decision "chose hexagonal arch (ADR-1)"
  python -m cdt.journal add --owner --kind plan "MVP first, auth in phase 2"
  python -m cdt.journal recall "why this architecture?"
  python -m cdt.journal log                 # dump the local mirror

Only works inside an enrolled project (run `cdt init` first).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

from .honcho_client import CONDUCTOR_PEER, OWNER_PEER, HonchoBackend
from .project import (daily_dir, diary_dir, docs_dir, find_project_root,
                      force_utf8, journal_dir, memory_dir, read_config,
                      records_dir)

KINDS = ("reasoning", "decision", "plan", "error", "solution", "checkpoint")

# Ingestion routes: each subtree of `.cdt/memory/` maps to a durable Honcho
# session, a peer (who authored it), and a `type` facet for recall. `docs/` is
# living knowledge (conductor); decisions are owner-authored (the human decides).
# `refs/` and `_index.md` stubs are deliberately absent — never ingested.
#   (subtree, session_suffix, peer, type)
INGEST_ROUTES = (
    ("docs", "docs", CONDUCTOR_PEER, "doc"),
    ("records/bugs", "bugs", CONDUCTOR_PEER, "bug"),
    ("records/decisions", "decisions", OWNER_PEER, "adr"),
    ("records/discovery", "discovery", CONDUCTOR_PEER, "grilling"),
    ("records/features", "features", CONDUCTOR_PEER, "feature"),
    ("records/gaps", "gaps", CONDUCTOR_PEER, "gap"),
)
# type -> session_suffix, for routing a `recall --type` to its durable session.
TYPE_TO_SESSION = {dtype: suffix for _, suffix, _, dtype in INGEST_ROUTES}


def _session_id(config: dict, override: Optional[str]) -> str:
    if override:
        return override
    prefix = config.get("honcho", {}).get("session_prefix", "cdt")
    return f"{prefix}-{datetime.date.today().isoformat()}"


def _mirror_path(root: Path, session_id: str) -> Path:
    journal_dir(root).mkdir(parents=True, exist_ok=True)
    return journal_dir(root) / f"{session_id}.jsonl"


def _write_mirror(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_mirror(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _session_prefix(config: dict) -> str:
    return config.get("honcho", {}).get("session_prefix", "cdt")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _manifest_path(root: Path) -> Path:
    return memory_dir(root) / ".ingest.json"


def _load_manifest(root: Path) -> dict:
    p = _manifest_path(root)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _save_manifest(root: Path, manifest: dict) -> None:
    _manifest_path(root).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")


def _doc_area(subtree: str, rel: str) -> Optional[str]:
    """Area facet for a doc: the first path segment under `docs/` (e.g.
    `docs/architecture/backend.md` -> "architecture"). None for flat records."""
    if subtree != "docs":
        return None
    parts = rel.split("/")            # memory-relative posix path
    return parts[1] if len(parts) >= 3 and parts[0] == "docs" else None


def cmd_ingest(root: Path, config: dict, args) -> int:
    """Walk `docs/` + `records/`, ingest changed files into Honcho (hash-idempotent).

    The manifest (`.cdt/memory/.ingest.json`) maps each memory-relative path to
    the content hash last ingested; unchanged files are skipped, deleted files
    are pruned. `refs/` and `_index.md` stubs are never touched.
    """
    mem = memory_dir(root)
    if not mem.is_dir():
        print(f"No memory tree at {mem} — run `cdt init` first.",
              file=sys.stderr)
        return 2
    manifest = _load_manifest(root)
    backend = HonchoBackend.from_config(config)
    prefix = _session_prefix(config)
    changed = skipped = failed = 0
    first_error: Optional[str] = None
    seen: set[str] = set()

    for subtree, suffix, peer, dtype in INGEST_ROUTES:
        base = mem / Path(subtree)
        if not base.is_dir():
            continue
        for md in sorted(base.rglob("*.md")):
            if md.name == "_index.md":
                continue
            rel = md.relative_to(mem).as_posix()
            seen.add(rel)
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                continue
            if not text.strip():
                continue
            h = _content_hash(text)
            if manifest.get(rel) == h and not args.force:
                skipped += 1
                continue
            meta = {"type": dtype, "path": rel, "hash": h}
            area = _doc_area(subtree, rel)
            if area:
                meta["area"] = area
            res = backend.add_doc(f"{prefix}-{suffix}", text,
                                  peer=peer, metadata=meta)
            if res.ok:
                manifest[rel] = h
                changed += 1
            else:
                failed += 1
                first_error = first_error or res.detail

    # Prune manifest entries for files that no longer exist.
    pruned = [rel for rel in manifest if rel not in seen]
    for rel in pruned:
        del manifest[rel]
    _save_manifest(root, manifest)

    print(f"ingest: {changed} ingested, {skipped} unchanged, "
          f"{failed} failed, {len(pruned)} pruned")
    if failed and first_error:
        print(f"  Honcho unavailable for {failed} file(s): {first_error}",
              file=sys.stderr)
    return 0


def cmd_digest(root: Path, config: dict, args) -> int:
    """Generate `daily/<date>.md` — a human digest of that day's diary entries.

    Pure derivation from `diary/<session>.jsonl`; safe to regenerate. Defaults
    to today's session; `--session` or `--all` widen the set.
    """
    if args.all:
        sessions = sorted(p.stem for p in diary_dir(root).glob("*.jsonl"))
    else:
        sessions = [_session_id(config, args.session)]
    daily_dir(root).mkdir(parents=True, exist_ok=True)
    written = 0
    for sid in sessions:
        entries = _read_mirror(_mirror_path(root, sid))
        if not entries:
            continue
        md = _render_digest(sid, entries)
        (daily_dir(root) / f"{sid}.md").write_text(md, encoding="utf-8")
        written += 1
    print(f"digest: {written} day(s) written to {daily_dir(root)}")
    return 0


def _render_digest(session_id: str, entries: List[dict]) -> str:
    """Group a day's entries by kind into a readable Markdown digest."""
    order = ("decision", "solution", "plan", "error", "reasoning")
    lines = [f"# {session_id}", "",
             f"_{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, "
             f"generated from the diary._", ""]
    by_kind: dict = {}
    for e in entries:
        by_kind.setdefault(e.get("kind", "reasoning"), []).append(e)
    for kind in (*order, *(k for k in by_kind if k not in order)):
        items = by_kind.get(kind)
        if not items:
            continue
        lines.append(f"## {kind.title()}")
        lines.append("")
        for e in items:
            gate = e.get("gate")
            tag = f"[gate {gate}] " if gate is not None else ""
            who = e.get("author", "conductor")
            lines.append(f"- {tag}{e.get('text', '').strip()} — _{who}_")
        lines.append("")
    return "\n".join(lines) + "\n"


def cmd_add(root: Path, config: dict, args) -> int:
    session_id = _session_id(config, args.session)
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "session": session_id,
        "author": "owner" if args.owner else "conductor",
        "kind": args.kind,
        "gate": args.gate,
        "text": args.text,
    }
    mirror = _mirror_path(root, session_id)
    _write_mirror(mirror, entry)

    backend = HonchoBackend.from_config(config)
    res = backend.add(session_id, args.text, gate=args.gate, kind=args.kind,
                      as_owner=args.owner)
    gate_s = f"gate {args.gate}" if args.gate is not None else "no gate"
    print(f"logged [{args.kind}/{gate_s}] -> {mirror.name}")
    if res.ok:
        print(f"  synced to Honcho (workspace '{backend.workspace}', session '{session_id}')")
    else:
        print(f"  Honcho unavailable, mirrored locally only: {res.detail}")

    # Keep CLAUDE.md's project memory live (best-effort, silent on failure).
    try:
        from .scaffold import refresh_claude_md
        if refresh_claude_md(root):
            print("  CLAUDE.md project memory refreshed")
    except Exception:  # noqa: BLE001
        pass
    return 0


def cmd_recall(root: Path, config: dict, args) -> int:
    # `--type` routes the query to that facet's durable session (e.g. `adr`
    # -> `<prefix>-decisions`); otherwise the day's diary session is used.
    if args.type:
        suffix = TYPE_TO_SESSION.get(args.type)
        if suffix is None:
            print(f"unknown --type '{args.type}'; choose from "
                  f"{', '.join(sorted(TYPE_TO_SESSION))}", file=sys.stderr)
            return 2
        session_id = f"{_session_prefix(config)}-{suffix}"
    else:
        session_id = _session_id(config, args.session)

    backend = HonchoBackend.from_config(config)
    res = backend.recall(session_id, args.question)
    if res.ok and res.text:
        print(res.text)
        return 0

    why = res.detail or "Honcho returned nothing"
    print(f"(Honcho recall unavailable: {why}) — scanning local memory\n",
          file=sys.stderr)
    terms = [t.lower() for t in args.question.split() if len(t) > 2]

    # Fallback A: the markdown memory (docs/records), honoring --type/--area.
    md_hits = _scan_markdown(root, terms, args.type, args.area)
    # Fallback B: the diary mirror (skipped when a doc-only filter is set).
    try:
        kinds = _parse_kinds(getattr(args, "kind", None))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    diary_hits = ([] if (args.type or args.area)
                  else _scan_diary(root, terms, args.gate, kinds))

    if not md_hits and not diary_hits:
        print("No matching memory.")
        return 0
    for path, snippet in md_hits[:args.k]:
        print(f"[{path}] {snippet}")
    for e in diary_hits[-args.k:]:
        g = f"gate {e['gate']}" if e.get("gate") is not None else "-"
        print(f"[{e.get('ts','')}] {e.get('author','')}/{e.get('kind','')}/{g}: "
              f"{e.get('text','')}")
    return 0


def _scan_diary(root: Path, terms: List[str], gate: Optional[int],
                kinds: Optional[set] = None) -> List[dict]:
    hits = []
    for jf in sorted(diary_dir(root).glob("*.jsonl")):
        for e in _read_mirror(jf):
            if gate is not None and e.get("gate") != gate:
                continue
            if kinds is not None and e.get("kind") not in kinds:
                continue
            blob = e.get("text", "").lower()
            if not terms or any(t in blob for t in terms):
                hits.append(e)
    return hits


def _scan_markdown(root: Path, terms: List[str], dtype: Optional[str],
                   area: Optional[str]) -> List[tuple]:
    """Keyword scan over ingested markdown (docs/records), filtered by facet.

    Returns (memory-relative path, first matching line) tuples. `_index.md`
    stubs and `refs/` are excluded — only what ingestion would have indexed.
    """
    mem = memory_dir(root)
    hits: List[tuple] = []
    for subtree, _suffix, _peer, route_type in INGEST_ROUTES:
        if dtype and route_type != dtype:
            continue
        base = mem / Path(subtree)
        if not base.is_dir():
            continue
        for md in sorted(base.rglob("*.md")):
            if md.name == "_index.md":
                continue
            rel = md.relative_to(mem).as_posix()
            if area and _doc_area(subtree, rel) != area:
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                continue
            low = text.lower()
            if terms and not any(t in low for t in terms):
                continue
            snippet = next((ln.strip() for ln in text.splitlines()
                            if ln.strip() and (not terms
                            or any(t in ln.lower() for t in terms))), "")
            hits.append((rel, snippet[:160]))
    return hits


def _parse_kinds(raw: Optional[str]) -> Optional[set]:
    """Parse a comma-separated --kind value into a validated set (or None)."""
    if not raw:
        return None
    kinds = {k.strip() for k in raw.split(",") if k.strip()}
    bad = kinds - set(KINDS)
    if bad:
        raise ValueError(f"unknown kind(s): {', '.join(sorted(bad))}; "
                         f"choose from {', '.join(KINDS)}")
    return kinds


def cmd_log(root: Path, config: dict, args) -> int:
    session_id = _session_id(config, args.session) if args.session else None
    files = ([_mirror_path(root, session_id)] if session_id
             else sorted(journal_dir(root).glob("*.jsonl")))
    try:
        kinds = _parse_kinds(getattr(args, "kind", None))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    gate = getattr(args, "gate", None)
    n = 0
    for jf in files:
        for e in _read_mirror(jf):
            if kinds is not None and e.get("kind") not in kinds:
                continue
            if gate is not None and e.get("gate") != gate:
                continue
            g = f"gate {e['gate']}" if e.get("gate") is not None else "-"
            print(f"[{e.get('ts','')}] {e.get('author','')}/{e.get('kind','')}/{g}: {e.get('text','')}")
            n += 1
    if n == 0:
        sel = (f" matching kind={','.join(sorted(kinds))}" if kinds else "") \
            + (f" gate={gate}" if gate is not None else "")
        print(f"No diary entries{sel}." if sel else "Diary empty.")
    return 0


# --- Honcho live memory: capture (observe) + inject (context) ----------------
# `observe` runs on Claude Code's UserPromptSubmit hook — it only appends the
# user's prompt to a local log (zero network, no latency). `context` runs on the
# SessionStart hook — it flushes pending observations to Honcho in one batch and
# prints what Honcho knows so Claude Code injects it. Capture is owner-only.

_OBS_KEEP = 500          # cap the local observation log
_OBS_FLUSH = 200         # max observations pushed to Honcho per session start
_CONTEXT_CAP = 1800      # max chars of injected context (token budget)
_CONTEXT_Q = ("Summarize, in a few bullet points, what you know about this "
              "project and about me (the owner) that is relevant to working "
              "here right now: my preferences and working style, the key "
              "decisions made, what is in progress, and known gotchas. Be "
              "concise; if you know little yet, say so briefly.")


def _hook_payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — a malformed/empty payload is a no-op
        return {}


def _observations_path(root: Path) -> Path:
    return memory_dir(root) / ".observations.jsonl"


def cmd_observe(root: Path, config: dict, args) -> int:
    """UserPromptSubmit hook: append the user's prompt locally (no network)."""
    payload = _hook_payload()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return 0
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
           "text": prompt, "synced": False}
    p = _observations_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if p.is_file():
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    lines.append(json.dumps(rec, ensure_ascii=False))
    p.write_text("\n".join(lines[-_OBS_KEEP:]) + "\n", encoding="utf-8")
    return 0  # silent: never add noise to the user's prompt turn


def _flush_observations(root: Path, config: dict) -> int:
    """Best-effort: push unsynced observations to Honcho (owner peer), batched."""
    p = _observations_path(root)
    if not p.is_file():
        return 0
    recs = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                recs.append(json.loads(ln))
            except ValueError:
                pass
    pending = [r for r in recs if not r.get("synced")]
    if not pending:
        return 0
    backend = HonchoBackend.from_config(config)
    session_id = _session_id(config, None)
    sent = 0
    for r in pending[:_OBS_FLUSH]:
        res = backend.add(session_id, r.get("text", ""), gate=None,
                          kind="observation", as_owner=True)
        if not res.ok:
            break               # Honcho down — keep them for the next flush
        r["synced"] = True
        sent += 1
    if sent:
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                               for r in recs[-_OBS_KEEP:]) + "\n", encoding="utf-8")
    return sent


def cmd_context(root: Path, config: dict, args) -> int:
    """SessionStart hook: flush observations, then print what Honcho remembers
    so Claude Code injects it into the session context. Silent on failure."""
    _flush_observations(root, config)
    backend = HonchoBackend.from_config(config)
    res = backend.recall(_session_id(config, None), _CONTEXT_Q)
    text = (res.text or "").strip() if res.ok else ""
    if not text:
        return 0                # nothing to inject (Honcho down or empty)
    if len(text) > _CONTEXT_CAP:
        text = text[:_CONTEXT_CAP].rstrip() + " …"
    print("## What Conductor's memory (Honcho) recalls about this project\n")
    print(text)
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Conductor per-project development diary.")
    ap.add_argument("--session", help="session id (default: <prefix>-<today>)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="record a diary entry")
    pa.add_argument("text", help="the entry text")
    pa.add_argument("--gate", type=int, help="flow gate number (1-11)")
    pa.add_argument("--kind", choices=KINDS, default="reasoning", help="entry kind")
    pa.add_argument("--owner", action="store_true", help="attribute to the owner (human)")

    pr = sub.add_parser("recall", help="recall past context by meaning")
    pr.add_argument("question", help="natural-language question")
    pr.add_argument("--type", choices=sorted(TYPE_TO_SESSION),
                    help="restrict to a memory facet (doc, adr, bug, ...)")
    pr.add_argument("--area", help="restrict docs to an area (e.g. architecture)")
    pr.add_argument("--kind", help="restrict the diary fallback to kind(s), "
                    "comma-separated (e.g. error,solution)")
    pr.add_argument("--gate", type=int, help="restrict the diary fallback to a gate")
    pr.add_argument("-k", type=int, default=8, help="max local fallback hits")

    pl = sub.add_parser("log", help="dump the local diary mirror")
    pl.add_argument("--kind", help="show only kind(s), comma-separated "
                    "(e.g. error,solution for solved problems)")
    pl.add_argument("--gate", type=int, help="show only a given flow gate")

    pi = sub.add_parser("ingest", help="ingest docs/records into Honcho (hash-idempotent)")
    pi.add_argument("--force", action="store_true",
                    help="re-ingest even unchanged files")

    pd = sub.add_parser("digest", help="generate daily/<date>.md from the diary")
    pd.add_argument("--all", action="store_true", help="digest every diary day")

    sub.add_parser("observe", help="(hook) capture the user's prompt to local memory")
    sub.add_parser("context", help="(hook) flush observations + print Honcho's context")

    args = ap.parse_args(argv)
    force_utf8()

    root = find_project_root()
    config = read_config(root)
    if config is None:
        # The hook commands must stay silent outside an enrolled project so they
        # never disrupt a Claude Code session in an unrelated directory.
        if args.cmd in ("observe", "context"):
            return 0
        print(f"ERROR: not an enrolled project (no .cdt/ at {root}). "
              "Run `cdt init` first.", file=sys.stderr)
        return 2

    if args.cmd == "add":
        return cmd_add(root, config, args)
    if args.cmd == "recall":
        return cmd_recall(root, config, args)
    if args.cmd == "log":
        return cmd_log(root, config, args)
    if args.cmd == "ingest":
        return cmd_ingest(root, config, args)
    if args.cmd == "digest":
        return cmd_digest(root, config, args)
    if args.cmd == "observe":
        return cmd_observe(root, config, args)
    if args.cmd == "context":
        return cmd_context(root, config, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
