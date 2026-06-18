#!/usr/bin/env python3
"""Invariant validator for Conductor's role templates.

Conductor is no longer a Claude Code plugin; it is a CLI that scaffolds role
Agents + Skills into projects. This validates the **templates** that get
scaffolded (`conductor/templates/`) and the role registry, so the source never
drifts. No third-party deps (stdlib only). Dual-mode:

  - CLI:    python tools/validate.py
  - import: from tools.validate import run; violations = run()
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # allow `import conductor.*` without install

TEMPLATES = ROOT / "conductor" / "templates"
AGENTS_DIR = TEMPLATES / "agents"
SKILLS_DIR = TEMPLATES / "skills"
FLOW = TEMPLATES / "flow.md"
PYPROJECT = ROOT / "pyproject.toml"

EXPECTED_ROLES = 36
EXPECTED_GATES = 11
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"  [{self.rule}] {self.path}: {self.message}"


# --- frontmatter parsing (minimal, no PyYAML) --------------------------------

def split_frontmatter(text: str):
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def frontmatter_field(fm: str, key: str):
    if fm is None:
        return None
    for line in fm.splitlines():
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


def _strip_quotes(value: str) -> str:
    if value and value[0] in "\"'" and value[-1] == value[0] and len(value) >= 2:
        return value[1:-1]
    return value


# --- rule registry -----------------------------------------------------------

RuleFn = Callable[["Context"], List[Violation]]
RULES: List[tuple] = []


def rule(rule_id: str, description: str):
    def deco(fn: RuleFn) -> RuleFn:
        RULES.append((rule_id, description, fn))
        return fn
    return deco


@dataclass
class Context:
    agent_files: List[Path]
    skill_files: List[Path]

    @classmethod
    def load(cls) -> "Context":
        agents = sorted(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.is_dir() else []
        skills = sorted(SKILLS_DIR.glob("*/SKILL.md")) if SKILLS_DIR.is_dir() else []
        return cls(agent_files=agents, skill_files=skills)

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            return str(p)


# --- R1: template parity -----------------------------------------------------

@rule("R1-parity", "36 agent templates + 36 skill templates, each with SKILL.md")
def check_parity(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    if len(ctx.agent_files) != EXPECTED_ROLES:
        v.append(Violation("R1-parity", ctx.rel(AGENTS_DIR),
                           f"expected {EXPECTED_ROLES} agents, found {len(ctx.agent_files)}"))
    if len(ctx.skill_files) != EXPECTED_ROLES:
        v.append(Violation("R1-parity", ctx.rel(SKILLS_DIR),
                           f"expected {EXPECTED_ROLES} skills, found {len(ctx.skill_files)}"))
    if SKILLS_DIR.is_dir():
        for d in sorted(SKILLS_DIR.iterdir()):
            if d.is_dir() and not (d / "SKILL.md").is_file():
                v.append(Violation("R1-parity", ctx.rel(d), "skill directory missing SKILL.md"))
    return v


# --- R2: frontmatter ---------------------------------------------------------

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@rule("R2-frontmatter", "frontmatter has name+description; kebab name == file/directory")
def check_frontmatter(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    targets = [(p, p.stem) for p in ctx.agent_files]
    targets += [(p, p.parent.name) for p in ctx.skill_files]
    for path, expected_slug in targets:
        rel = ctx.rel(path)
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if fm is None:
            v.append(Violation("R2-frontmatter", rel, "missing YAML frontmatter"))
            continue
        name = frontmatter_field(fm, "name")
        if name is None:
            v.append(Violation("R2-frontmatter", rel, "frontmatter missing 'name'"))
        else:
            name = _strip_quotes(name)
            if not KEBAB_RE.match(name):
                v.append(Violation("R2-frontmatter", rel, f"name '{name}' is not kebab-case"))
            elif name != expected_slug:
                v.append(Violation("R2-frontmatter", rel, f"name '{name}' != expected '{expected_slug}'"))
        desc = frontmatter_field(fm, "description")
        if desc is None:
            v.append(Violation("R2-frontmatter", rel, "frontmatter missing 'description'"))
        elif not _strip_quotes(desc).strip():
            v.append(Violation("R2-frontmatter", rel, "description is empty"))
    return v


# --- R3: YAML safety ---------------------------------------------------------

DQUOTED_RE = re.compile(r'^"(?:\\.|[^"\\])*"$')


@rule("R3-yaml-safety", "description double-quoted, escaped, and parseable")
def check_yaml_safety(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in list(ctx.agent_files) + list(ctx.skill_files):
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        desc = frontmatter_field(fm, "description")
        if desc is None:
            continue
        if not desc.startswith('"'):
            v.append(Violation("R3-yaml-safety", ctx.rel(path),
                               "description is not double-quoted"))
        elif not DQUOTED_RE.match(desc):
            v.append(Violation("R3-yaml-safety", ctx.rel(path),
                               'description has unescaped internal quotes (use \\")'))
    return v


# --- R4: pyproject version (semver) ------------------------------------------

@rule("R4-version", "pyproject.toml has a valid semver version")
def check_version(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    if not PYPROJECT.is_file():
        return [Violation("R4-version", "pyproject.toml", "file not found")]
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"))
    if not m:
        v.append(Violation("R4-version", "pyproject.toml", "missing version field"))
    elif not SEMVER_RE.match(m.group(1)):
        v.append(Violation("R4-version", "pyproject.toml",
                           f"version '{m.group(1)}' is not semver"))
    return v


# --- R5: agent anchor --------------------------------------------------------

MIN_PROMPT_CHARS = 200
LIVROS_RE = re.compile(r"\*\*Reference books:\*\*")


@rule("R5-agent-anchor", "agent has a system prompt and a **Reference books:** line")
def check_agent_anchor(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in ctx.agent_files:
        _fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
        if not LIVROS_RE.search(body):
            v.append(Violation("R5-agent-anchor", ctx.rel(path), "missing **Reference books:** line"))
        prompt = LIVROS_RE.split(body)[0].strip()
        if len(prompt) < MIN_PROMPT_CHARS:
            v.append(Violation("R5-agent-anchor", ctx.rel(path),
                               f"system prompt too short ({len(prompt)} < {MIN_PROMPT_CHARS})"))
    return v


# --- R6: skill structure -----------------------------------------------------

QUANDO_RE = re.compile(r"(?im)^\W*When to use")
NUM_STEP_RE = re.compile(r"(?m)^\s*\d+\.\s+\S")
MIN_STEPS = 2


@rule("R6-skill-structure", "skill has 'When to use' and numbered steps")
def check_skill_structure(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in ctx.skill_files:
        _fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
        if not QUANDO_RE.search(body):
            v.append(Violation("R6-skill-structure", ctx.rel(path), "missing 'When to use'"))
        if len(NUM_STEP_RE.findall(body)) < MIN_STEPS:
            v.append(Violation("R6-skill-structure", ctx.rel(path),
                               f"insufficient numbered steps (< {MIN_STEPS})"))
    return v


# --- R7: roles registry + flow integrity -------------------------------------

GATE_RE = re.compile(r"(?m)^##\s*Gate\s+(\d+)\s*—")


@rule("R7-roles-flow", "roles.py resolves to real templates; flow.md has 11 gates")
def check_roles_flow(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    try:
        from conductor.roles import ROLES
    except Exception as e:  # noqa: BLE001
        return [Violation("R7-roles-flow", "conductor/roles.py", f"cannot import: {e}")]

    if len(ROLES) != EXPECTED_ROLES:
        v.append(Violation("R7-roles-flow", "conductor/roles.py",
                           f"registry has {len(ROLES)} roles, expected {EXPECTED_ROLES}"))
    agent_slugs = {p.stem for p in ctx.agent_files}
    skill_slugs = {p.parent.name for p in ctx.skill_files}
    for slug, role in ROLES.items():
        if slug not in agent_slugs:
            v.append(Violation("R7-roles-flow", "conductor/roles.py",
                               f"role '{slug}' has no agent template"))
        if role.skill not in skill_slugs:
            v.append(Violation("R7-roles-flow", "conductor/roles.py",
                               f"role '{slug}' -> missing skill template '{role.skill}'"))
    # each skill template is claimed by exactly one role (1:1 pairing)
    claimed = [r.skill for r in ROLES.values()]
    if len(set(claimed)) != len(claimed):
        v.append(Violation("R7-roles-flow", "conductor/roles.py", "a skill is paired to >1 role"))

    if not FLOW.is_file():
        v.append(Violation("R7-roles-flow", "conductor/templates/flow.md", "flow.md not found"))
    else:
        gates = sorted(int(n) for n in GATE_RE.findall(FLOW.read_text(encoding="utf-8")))
        if gates != list(range(1, EXPECTED_GATES + 1)):
            v.append(Violation("R7-roles-flow", "conductor/templates/flow.md",
                               f"gates {gates} != 1..{EXPECTED_GATES}"))
    return v


# --- R8: agent model tier ----------------------------------------------------

VALID_MODELS = {"opus", "sonnet", "haiku"}


@rule("R8-agent-model", "agent declares model: one of opus|sonnet|haiku")
def check_agent_model(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in ctx.agent_files:
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        model = frontmatter_field(fm, "model")
        if model is None:
            v.append(Violation("R8-agent-model", ctx.rel(path), "frontmatter missing 'model'"))
            continue
        if _strip_quotes(model) not in VALID_MODELS:
            v.append(Violation("R8-agent-model", ctx.rel(path),
                               f"model '{_strip_quotes(model)}' not in {sorted(VALID_MODELS)}"))
    return v


# --- R9: memory tree <-> ingestion routing consistency -----------------------

@rule("R9-memory-routing", "ingest routes map to scaffolded folders; refs/ never ingested")
def check_memory_routing(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    where = "conductor/journal.py"
    try:
        from conductor.scaffold import MEMORY_TREE, MEMORY_LOCAL
        from conductor.journal import INGEST_ROUTES, TYPE_TO_SESSION
    except Exception as e:  # noqa: BLE001
        return [Violation("R9-memory-routing", where, f"cannot import: {e}")]

    tree = set(MEMORY_TREE)
    types = [dtype for _, _, _, dtype in INGEST_ROUTES]
    for subtree, suffix, _peer, dtype in INGEST_ROUTES:
        # A route may target a leaf folder or a parent of several (e.g. `docs`
        # covers `docs/architecture`, `docs/api`, ...).
        covered = subtree in tree or any(k.startswith(subtree + "/") for k in tree)
        if not covered:
            v.append(Violation("R9-memory-routing", where,
                               f"route '{subtree}' is not a folder in scaffold.MEMORY_TREE"))
        if subtree.startswith("refs/"):
            v.append(Violation("R9-memory-routing", where,
                               f"route '{subtree}' ingests refs/ (must never be ingested)"))
        if subtree in ("diary", "daily"):
            v.append(Violation("R9-memory-routing", where,
                               f"route '{subtree}' is local-only, not a document subtree"))
        if TYPE_TO_SESSION.get(dtype) != suffix:
            v.append(Violation("R9-memory-routing", where,
                               f"TYPE_TO_SESSION['{dtype}'] != route suffix '{suffix}'"))
    if len(set(types)) != len(types):
        v.append(Violation("R9-memory-routing", where, "duplicate ingest type across routes"))
    # local-only folders must be git-ignored (no leakage of diary/digests/cache)
    for needed in ("memory/diary/", "memory/daily/"):
        if needed not in set(MEMORY_LOCAL):
            v.append(Violation("R9-memory-routing", "conductor/scaffold.py",
                               f"'{needed}' missing from MEMORY_LOCAL (git-ignore)"))
    return v


# --- R10: /cdt flow driver command -------------------------------------------

DRIVER = TEMPLATES / "commands" / "cdt.md"
DRIVER_ANCHORS = ("AskUserQuestion", "Task tool", "conductor library",
                  "conductor journal", "HALT")


@rule("R10-flow-driver", "/cdt driver command exists and enforces RAG + delegation + checkpoint")
def check_flow_driver(ctx: Context) -> List[Violation]:
    rel = "conductor/templates/commands/cdt.md"
    if not DRIVER.is_file():
        return [Violation("R10-flow-driver", rel, "driver command not found")]
    text = DRIVER.read_text(encoding="utf-8")
    fm, _ = split_frontmatter(text)
    v: List[Violation] = []
    if frontmatter_field(fm, "description") is None:
        v.append(Violation("R10-flow-driver", rel, "frontmatter missing 'description'"))
    for anchor in DRIVER_ANCHORS:
        if anchor not in text:
            v.append(Violation("R10-flow-driver", rel,
                               f"driver missing enforcement anchor: '{anchor}'"))
    return v


# --- runner ------------------------------------------------------------------

def run() -> List[Violation]:
    ctx = Context.load()
    violations: List[Violation] = []
    for _id, _desc, fn in RULES:
        violations.extend(fn(ctx))
    return violations


def main(argv: List[str]) -> int:
    violations = run()
    by_rule: Dict[str, int] = {}
    for vi in violations:
        by_rule[vi.rule] = by_rule.get(vi.rule, 0) + 1
    print(f"Conductor validate — {len(RULES)} rule(s), {len(violations)} violation(s)")
    for rule_id, desc, _fn in RULES:
        n = by_rule.get(rule_id, 0)
        print(f"  [{'OK  ' if n == 0 else 'FAIL'}] {rule_id}: {desc}" + (f"  ({n})" if n else ""))
    if violations:
        print("\nViolations:")
        for vi in violations:
            print(vi)
        return 1
    print("\nAll invariants passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
