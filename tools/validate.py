#!/usr/bin/env python3
"""Invariant validator for the Conductor plugin.

Encodes the "golden rules" that keep the plugin consistent with `plano.md`
(source of truth) as executable code. Each rule is a function registered via
`@rule(...)`; running this file executes all rules and fails (exit code 1) if
any invariant is violated.

No third-party dependencies (stdlib only). Dual-mode:

  - CLI:    python tools/validate.py
  - import: from tools.validate import run; violations = run()
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
COMMANDS_DIR = ROOT / "commands"
CONDUCTOR_CMD = COMMANDS_DIR / "cdt.md"
PLANO = ROOT / "plano.md"

EXPECTED_GATES = 11
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
PYPROJECT = ROOT / "pyproject.toml"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

EXPECTED_ROLES = 36


@dataclass(frozen=True)
class Violation:
    """An invariant violation: which rule, in which file, and the reason."""

    rule: str
    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        rel = self.path
        return f"  [{self.rule}] {rel}: {self.message}"


# --- utility parsing (minimal YAML frontmatter, no PyYAML) -------------------

def split_frontmatter(text: str):
    """Returns (frontmatter_str, body_str) or (None, text) if none found.

    Frontmatter = block between the first and second `---` line.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            return fm, body
    return None, text


def frontmatter_field(fm: str, key: str):
    """Raw value (with quotes, if any) of the first `key:` line in the frontmatter."""
    if fm is None:
        return None
    for line in fm.splitlines():
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


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
    """Files loaded once, shared across all rules."""

    agent_files: List[Path]
    skill_files: List[Path]
    plano_text: str

    @classmethod
    def load(cls) -> "Context":
        agents = sorted(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.is_dir() else []
        skills = sorted(SKILLS_DIR.glob("*/SKILL.md")) if SKILLS_DIR.is_dir() else []
        plano = PLANO.read_text(encoding="utf-8") if PLANO.is_file() else ""
        return cls(agent_files=agents, skill_files=skills, plano_text=plano)

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            return str(p)


# --- R1: plan <-> source parity ---------------------------------------------

@rule("R1-parity", "36 agents + 36 skills, each with SKILL.md; plan names 36 skills")
def check_parity(ctx: Context) -> List[Violation]:
    v: List[Violation] = []

    n_agents = len(ctx.agent_files)
    if n_agents != EXPECTED_ROLES:
        v.append(Violation("R1-parity", ctx.rel(AGENTS_DIR),
                           f"expected {EXPECTED_ROLES} agents, found {n_agents}"))

    n_skills = len(ctx.skill_files)
    if n_skills != EXPECTED_ROLES:
        v.append(Violation("R1-parity", ctx.rel(SKILLS_DIR),
                           f"expected {EXPECTED_ROLES} skills, found {n_skills}"))

    # Skill directories missing SKILL.md.
    if SKILLS_DIR.is_dir():
        for d in sorted(SKILLS_DIR.iterdir()):
            if d.is_dir() and not (d / "SKILL.md").is_file():
                v.append(Violation("R1-parity", ctx.rel(d), "skill directory missing SKILL.md"))

    # Sanity on the plan itself: it still names 36 skills. (The dir slugs are
    # English now while plano.md stays pt-BR, so we no longer map name -> dir.)
    plano_skills = set(re.findall(r"\*\*Skill\s*—\s*`([a-z0-9_]+)`", ctx.plano_text))
    if plano_skills and len(plano_skills) != EXPECTED_ROLES:
        v.append(Violation("R1-parity", "plano.md",
                           f"plan names {len(plano_skills)} skills, expected {EXPECTED_ROLES}"))

    return v


# --- R2: frontmatter (name + description; name kebab == file/directory) ------

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _strip_quotes(value: str) -> str:
    if value and value[0] in "\"'" and value[-1] == value[0] and len(value) >= 2:
        return value[1:-1]
    return value


@rule("R2-frontmatter", "frontmatter has name+description; kebab name == file/directory")
def check_frontmatter(ctx: Context) -> List[Violation]:
    v: List[Violation] = []

    # (file, expected_slug) — agent uses filename stem; skill uses its directory name.
    targets = [(p, p.stem) for p in ctx.agent_files]
    targets += [(p, p.parent.name) for p in ctx.skill_files]

    for path, expected_slug in targets:
        rel = ctx.rel(path)
        text = path.read_text(encoding="utf-8")
        fm, _body = split_frontmatter(text)
        if fm is None:
            v.append(Violation("R2-frontmatter", rel, "missing YAML frontmatter (--- ... ---)"))
            continue

        name = frontmatter_field(fm, "name")
        if name is None:
            v.append(Violation("R2-frontmatter", rel, "frontmatter missing 'name' field"))
        else:
            name = _strip_quotes(name)
            if not KEBAB_RE.match(name):
                v.append(Violation("R2-frontmatter", rel, f"name '{name}' is not kebab-case"))
            elif name != expected_slug:
                v.append(Violation("R2-frontmatter", rel,
                                   f"name '{name}' != expected '{expected_slug}'"))

        desc = frontmatter_field(fm, "description")
        if desc is None:
            v.append(Violation("R2-frontmatter", rel, "frontmatter missing 'description' field"))
        elif not _strip_quotes(desc).strip():
            v.append(Violation("R2-frontmatter", rel, "description is empty"))

    return v


# --- R3: YAML safety (description quoted and parseable) ----------------------

# Double-quoted YAML scalar: internal quotes must be escaped as \".
DQUOTED_RE = re.compile(r'^"(?:\\.|[^"\\])*"$')


@rule("R3-yaml-safety", "description double-quoted, escaped, and parseable")
def check_yaml_safety(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in list(ctx.agent_files) + list(ctx.skill_files):
        rel = ctx.rel(path)
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        desc = frontmatter_field(fm, "description")
        if desc is None:
            continue  # absence is a R2 problem, not R3
        if not desc.startswith('"'):
            v.append(Violation("R3-yaml-safety", rel,
                               "description is not double-quoted (risk of breaking the parser)"))
        elif not DQUOTED_RE.match(desc):
            v.append(Violation("R3-yaml-safety", rel,
                               'description has unescaped internal quotes (use \\")'))
    return v


# --- R4: version sync (plugin.json == pyproject.toml, semver) ----------------

@rule("R4-version-sync", "plugin.json and pyproject.toml on the same semver version")
def check_version_sync(ctx: Context) -> List[Violation]:
    v: List[Violation] = []

    plugin_ver = None
    if PLUGIN_JSON.is_file():
        try:
            plugin_ver = json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version")
        except (ValueError, OSError) as e:
            v.append(Violation("R4-version-sync", ctx.rel(PLUGIN_JSON), f"invalid JSON: {e}"))
    else:
        v.append(Violation("R4-version-sync", ctx.rel(PLUGIN_JSON), "file not found"))

    pyproj_ver = None
    if PYPROJECT.is_file():
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"))
        pyproj_ver = m.group(1) if m else None
        if pyproj_ver is None:
            v.append(Violation("R4-version-sync", ctx.rel(PYPROJECT), "missing version field"))
    else:
        v.append(Violation("R4-version-sync", ctx.rel(PYPROJECT), "file not found"))

    for label, ver, path in (("plugin.json", plugin_ver, PLUGIN_JSON),
                             ("pyproject.toml", pyproj_ver, PYPROJECT)):
        if ver is not None and not SEMVER_RE.match(ver):
            v.append(Violation("R4-version-sync", ctx.rel(path),
                               f"version '{ver}' is not semver MAJOR.MINOR.PATCH"))

    if plugin_ver is not None and pyproj_ver is not None and plugin_ver != pyproj_ver:
        v.append(Violation("R4-version-sync", ctx.rel(PYPROJECT),
                           f"version {pyproj_ver} != plugin.json {plugin_ver}"))

    return v


# --- R5: agent anchor (system prompt + Reference books) ----------------------

MIN_PROMPT_CHARS = 200
LIVROS_RE = re.compile(r"\*\*Reference books:\*\*")


@rule("R5-agent-anchor", "agent has a system prompt and a **Reference books:** line")
def check_agent_anchor(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in ctx.agent_files:
        rel = ctx.rel(path)
        _fm, body = split_frontmatter(path.read_text(encoding="utf-8"))

        if not LIVROS_RE.search(body):
            v.append(Violation("R5-agent-anchor", rel, "missing **Reference books:** line"))

        # Prompt = body before the Reference books line; must be substantial.
        prompt = LIVROS_RE.split(body)[0].strip()
        if len(prompt) < MIN_PROMPT_CHARS:
            v.append(Violation("R5-agent-anchor", rel,
                               f"system prompt too short ({len(prompt)} < {MIN_PROMPT_CHARS} chars)"))
    return v


# --- R6: skill structure ('When to use' + numbered steps) -------------------

QUANDO_RE = re.compile(r"(?im)^\W*When to use")
NUM_STEP_RE = re.compile(r"(?m)^\s*\d+\.\s+\S")
MIN_STEPS = 2


@rule("R6-skill-structure", "skill has 'When to use' and numbered steps")
def check_skill_structure(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in ctx.skill_files:
        rel = ctx.rel(path)
        _fm, body = split_frontmatter(path.read_text(encoding="utf-8"))

        if not QUANDO_RE.search(body):
            v.append(Violation("R6-skill-structure", rel, "missing 'When to use' section"))

        n_steps = len(NUM_STEP_RE.findall(body))
        if n_steps < MIN_STEPS:
            v.append(Violation("R6-skill-structure", rel,
                               f"insufficient numbered steps ({n_steps} < {MIN_STEPS})"))
    return v


# --- R7: /conductor flow integrity -------------------------------------------

GATE_RE = re.compile(r"(?m)^##\s*Gate\s+(\d+)\s*—")
BACKTICK_RE = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")


@rule("R7-flow-integrity", "/cdt has 11 gates and only references real roles/skills/commands")
def check_flow_integrity(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    if not CONDUCTOR_CMD.is_file():
        v.append(Violation("R7-flow-integrity", ctx.rel(CONDUCTOR_CMD), "/conductor command not found"))
        return v

    text = CONDUCTOR_CMD.read_text(encoding="utf-8")
    _fm, body = split_frontmatter(text)

    gates = [int(n) for n in GATE_RE.findall(body)]
    if sorted(gates) != list(range(1, EXPECTED_GATES + 1)):
        v.append(Violation("R7-flow-integrity", ctx.rel(CONDUCTOR_CMD),
                           f"gates {sorted(gates)} != 1..{EXPECTED_GATES}"))

    # Backtick tokens must be an existing agent, skill, OR command.
    agent_slugs = {p.stem for p in ctx.agent_files}
    skill_slugs = {p.parent.name for p in ctx.skill_files}
    command_slugs = {p.stem for p in COMMANDS_DIR.glob("*.md")} if COMMANDS_DIR.is_dir() else set()
    known = agent_slugs | skill_slugs | command_slugs
    for token in sorted(set(BACKTICK_RE.findall(body))):
        if token not in known:
            v.append(Violation("R7-flow-integrity", ctx.rel(CONDUCTOR_CMD),
                               f"reference `{token}` is not an existing agent or skill"))
    return v


# --- runner ------------------------------------------------------------------

def run() -> List[Violation]:
    """Run all rules and return the flat list of violations."""
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
        mark = "OK  " if n == 0 else "FAIL"
        print(f"  [{mark}] {rule_id}: {desc}" + (f"  ({n})" if n else ""))

    if violations:
        print("\nViolations:")
        for vi in violations:
            print(vi)
        return 1
    print("\nAll invariants passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
