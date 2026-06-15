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
import json
import sys
from pathlib import Path
from typing import List, Optional

from .honcho_client import HonchoBackend
from .project import (find_project_root, force_utf8, journal_dir, read_config)

KINDS = ("reasoning", "decision", "plan", "error", "solution")


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
    session_id = _session_id(config, args.session)
    backend = HonchoBackend.from_config(config)
    res = backend.recall(session_id, args.question)
    if res.ok and res.text:
        print(res.text)
        return 0

    # Fallback: keyword scan of the local mirror across all sessions.
    why = res.detail or "Honcho returned nothing"
    print(f"(Honcho recall unavailable: {why}) — scanning local mirror\n", file=sys.stderr)
    terms = [t.lower() for t in args.question.split() if len(t) > 2]
    hits = []
    for jf in sorted(journal_dir(root).glob("*.jsonl")):
        for e in _read_mirror(jf):
            if args.gate is not None and e.get("gate") != args.gate:
                continue
            blob = e.get("text", "").lower()
            if not terms or any(t in blob for t in terms):
                hits.append(e)
    if not hits:
        print("No matching diary entries.")
        return 0
    for e in hits[-args.k:]:
        g = f"gate {e['gate']}" if e.get("gate") is not None else "-"
        print(f"[{e.get('ts','')}] {e.get('author','')}/{e.get('kind','')}/{g}: {e.get('text','')}")
    return 0


def cmd_log(root: Path, config: dict, args) -> int:
    session_id = _session_id(config, args.session) if args.session else None
    files = ([_mirror_path(root, session_id)] if session_id
             else sorted(journal_dir(root).glob("*.jsonl")))
    n = 0
    for jf in files:
        for e in _read_mirror(jf):
            g = f"gate {e['gate']}" if e.get("gate") is not None else "-"
            print(f"[{e.get('ts','')}] {e.get('author','')}/{e.get('kind','')}/{g}: {e.get('text','')}")
            n += 1
    if n == 0:
        print("Diary empty.")
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
    pr.add_argument("--gate", type=int, help="restrict the local fallback to a gate")
    pr.add_argument("-k", type=int, default=8, help="max local fallback hits")

    sub.add_parser("log", help="dump the local diary mirror")

    args = ap.parse_args(argv)
    force_utf8()

    root = find_project_root()
    config = read_config(root)
    if config is None:
        print(f"ERROR: not an enrolled project (no .cdt/ at {root}). "
              "Run `python -m cdt.init` (or `/cdt init`) first.", file=sys.stderr)
        return 2

    if args.cmd == "add":
        return cmd_add(root, config, args)
    if args.cmd == "recall":
        return cmd_recall(root, config, args)
    if args.cmd == "log":
        return cmd_log(root, config, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
