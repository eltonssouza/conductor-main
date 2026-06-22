#!/usr/bin/env python3
"""`python tools/simulate-selection.py` — preview version-aware corpus selection.

Builds a synthetic, version-tagged catalog (so you can try this BEFORE the real
books exist) and runs the same `select_corpus` the ingest uses. Pick versions and
see which book edition each stack resolves to — nearest major wins (ties prefer
the higher).

    python tools/simulate-selection.py --stacks java@25,spring@4,angular@21
    python tools/simulate-selection.py --stacks angular@19        # -> nearest edition
    python tools/simulate-selection.py --stacks all               # every edition
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conductor.rag.core import select_corpus  # noqa: E402

# (path, frontmatter) — a stand-in corpus with multiple editions per stack.
CATALOG = {
    "03_design_and_architecture/Clean Architecture - Martin.md": {"software_dev": "core"},
    "04_engineering_and_practices/The Pragmatic Programmer.md":   {"software_dev": "core"},
    "01_programming_languages/Java SE 17 - Horstmann.md":   {"software_dev": "stack", "stack": "java", "version": "17"},
    "01_programming_languages/Java SE 21 - Horstmann.md":   {"software_dev": "stack", "stack": "java", "version": "21"},
    "01_programming_languages/Core Java 25 - Horstmann.md": {"software_dev": "stack", "stack": "java", "version": "25"},
    "01_programming_languages/The Go Programming Language.md": {"software_dev": "stack", "stack": "go"},  # unversioned
    "01_programming_languages/Python Crash Course.md":        {"software_dev": "stack", "stack": "python", "version": "3"},
    "14_frameworks/Angular 18 - Guide.md": {"software_dev": "stack", "stack": "angular", "version": "18"},
    "14_frameworks/Angular 22 - Guide.md": {"software_dev": "stack", "stack": "angular", "version": "22"},
    "14_frameworks/Spring Boot 3 in Action.md": {"software_dev": "stack", "stack": "spring", "version": "3"},
    "14_frameworks/Spring Boot 4 in Action.md": {"software_dev": "stack", "stack": "spring", "version": "4"},
    "07_devops_sre_operations/The DevOps Handbook.md": {"software_dev": "supporting"},
}


def main() -> int:
    ap = argparse.ArgumentParser(prog="simulate-selection")
    ap.add_argument("--stacks", default="java@25,spring@4,angular@21",
                    help="comma list of stack[@version] (or 'all')")
    ap.add_argument("--tiers", default="core", help="comma list of software_dev tiers")
    args = ap.parse_args()
    stacks = [s.strip() for s in args.stacks.split(",") if s.strip()]
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]

    chosen = select_corpus(CATALOG, tiers, stacks)

    print(f"\nSelection:  stacks={args.stacks}   tiers={args.tiers}")
    print("=" * 64)
    print("Catalog (synthetic) and what gets ingested:\n")
    for path, fm in CATALOG.items():
        tag = fm.get("stack", "")
        ver = fm.get("version", "")
        label = f"{tag} {ver}".strip() if tag else fm.get("software_dev", "")
        mark = "  ✓ INGEST " if path in chosen else "  · skip   "
        print(f"{mark} [{label:<12}] {Path(path).name}")

    print("\nResolved per requested stack:")
    for s in stacks:
        sid = s.split("@")[0].lower()
        if sid == "all":
            print("  all -> every edition of every stack")
            continue
        hits = [Path(p).name for p, fm in CATALOG.items()
                if (fm.get("stack", "").lower() == sid and p in chosen)]
        print(f"  {s:<14} -> {', '.join(hits) or '(no book for this stack)'}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
