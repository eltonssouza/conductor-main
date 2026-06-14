#!/usr/bin/env python3
"""Validador de invariantes do plugin Conductor.

Codifica como código executável as "regras de ouro" que mantêm o plugin
coerente com o `plano.md` (fonte da verdade). Cada regra é uma função
registrada via `@rule(...)`; rodar este arquivo executa todas e falha
(exit code 1) se qualquer invariante for violada.

Sem dependências de terceiros (apenas stdlib). Uso duplo:

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
PLANO = ROOT / "plano.md"
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
PYPROJECT = ROOT / "pyproject.toml"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

EXPECTED_ROLES = 36


@dataclass(frozen=True)
class Violation:
    """Uma quebra de invariante: qual regra, em qual arquivo, e o motivo."""

    rule: str
    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - formatação trivial
        rel = self.path
        return f"  [{self.rule}] {rel}: {self.message}"


# --- parsing utilitário (frontmatter YAML mínimo, sem PyYAML) ----------------

def split_frontmatter(text: str):
    """Devolve (frontmatter_str, corpo_str) ou (None, text) se não houver.

    Frontmatter = bloco entre a primeira e a segunda linha `---`.
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
    """Valor cru (com aspas, se houver) da primeira linha `key:` do frontmatter."""
    if fm is None:
        return None
    for line in fm.splitlines():
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


# --- registro de regras ------------------------------------------------------

RuleFn = Callable[["Context"], List[Violation]]
RULES: List[tuple] = []


def rule(rule_id: str, description: str):
    def deco(fn: RuleFn) -> RuleFn:
        RULES.append((rule_id, description, fn))
        return fn

    return deco


@dataclass
class Context:
    """Arquivos carregados uma vez, compartilhados por todas as regras."""

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


# --- R1: paridade plano <-> fonte -------------------------------------------

@rule("R1-parity", "36 agentes + 36 skills; toda skill do plano tem diretório")
def check_parity(ctx: Context) -> List[Violation]:
    v: List[Violation] = []

    n_agents = len(ctx.agent_files)
    if n_agents != EXPECTED_ROLES:
        v.append(Violation("R1-parity", ctx.rel(AGENTS_DIR),
                           f"esperado {EXPECTED_ROLES} agentes, encontrado {n_agents}"))

    n_skills = len(ctx.skill_files)
    if n_skills != EXPECTED_ROLES:
        v.append(Violation("R1-parity", ctx.rel(SKILLS_DIR),
                           f"esperado {EXPECTED_ROLES} skills, encontrado {n_skills}"))

    # Diretórios de skill sem SKILL.md.
    if SKILLS_DIR.is_dir():
        for d in sorted(SKILLS_DIR.iterdir()):
            if d.is_dir() and not (d / "SKILL.md").is_file():
                v.append(Violation("R1-parity", ctx.rel(d), "diretório de skill sem SKILL.md"))

    # Toda skill nomeada no plano (`**Skill — `nome`:**`) tem um diretório.
    plano_skills = set(re.findall(r"\*\*Skill\s*—\s*`([a-z0-9_]+)`", ctx.plano_text))
    existing_dirs = {p.parent.name for p in ctx.skill_files}
    for name in sorted(plano_skills):
        kebab = name.replace("_", "-")
        if kebab not in existing_dirs:
            v.append(Violation("R1-parity", "plano.md",
                               f"skill `{name}` do plano sem diretório skills/{kebab}/"))

    if plano_skills and len(plano_skills) != EXPECTED_ROLES:
        v.append(Violation("R1-parity", "plano.md",
                           f"plano nomeia {len(plano_skills)} skills, esperado {EXPECTED_ROLES}"))

    return v


# --- R2: frontmatter (name + description; name kebab == arquivo/diretório) ---

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _strip_quotes(value: str) -> str:
    if value and value[0] in "\"'" and value[-1] == value[0] and len(value) >= 2:
        return value[1:-1]
    return value


@rule("R2-frontmatter", "frontmatter com name+description; name kebab == arquivo/diretório")
def check_frontmatter(ctx: Context) -> List[Violation]:
    v: List[Violation] = []

    # (arquivo, slug_esperado) — agente usa nome do arquivo; skill usa o diretório.
    targets = [(p, p.stem) for p in ctx.agent_files]
    targets += [(p, p.parent.name) for p in ctx.skill_files]

    for path, expected_slug in targets:
        rel = ctx.rel(path)
        text = path.read_text(encoding="utf-8")
        fm, _body = split_frontmatter(text)
        if fm is None:
            v.append(Violation("R2-frontmatter", rel, "sem frontmatter YAML (--- ... ---)"))
            continue

        name = frontmatter_field(fm, "name")
        if name is None:
            v.append(Violation("R2-frontmatter", rel, "frontmatter sem campo name"))
        else:
            name = _strip_quotes(name)
            if not KEBAB_RE.match(name):
                v.append(Violation("R2-frontmatter", rel, f"name '{name}' não é kebab-case"))
            elif name != expected_slug:
                v.append(Violation("R2-frontmatter", rel,
                                   f"name '{name}' != esperado '{expected_slug}'"))

        desc = frontmatter_field(fm, "description")
        if desc is None:
            v.append(Violation("R2-frontmatter", rel, "frontmatter sem campo description"))
        elif not _strip_quotes(desc).strip():
            v.append(Violation("R2-frontmatter", rel, "description vazia"))

    return v


# --- R3: segurança YAML (description aspeada e parseável) --------------------

# Escalar YAML entre aspas duplas: aspas internas devem vir escapadas como \".
DQUOTED_RE = re.compile(r'^"(?:\\.|[^"\\])*"$')


@rule("R3-yaml-safety", "description entre aspas duplas, escapada e parseável")
def check_yaml_safety(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in list(ctx.agent_files) + list(ctx.skill_files):
        rel = ctx.rel(path)
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        desc = frontmatter_field(fm, "description")
        if desc is None:
            continue  # ausência é problema de R2, não de R3
        if not desc.startswith('"'):
            v.append(Violation("R3-yaml-safety", rel,
                               "description não está entre aspas duplas (risco de quebrar o parser)"))
        elif not DQUOTED_RE.match(desc):
            v.append(Violation("R3-yaml-safety", rel,
                               'description com aspas internas não escapadas (use \\")'))
    return v


# --- R4: versão sincronizada (plugin.json == pyproject.toml, semver) ---------

@rule("R4-version-sync", "plugin.json e pyproject.toml na mesma versão semver")
def check_version_sync(ctx: Context) -> List[Violation]:
    v: List[Violation] = []

    plugin_ver = None
    if PLUGIN_JSON.is_file():
        try:
            plugin_ver = json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version")
        except (ValueError, OSError) as e:
            v.append(Violation("R4-version-sync", ctx.rel(PLUGIN_JSON), f"JSON inválido: {e}"))
    else:
        v.append(Violation("R4-version-sync", ctx.rel(PLUGIN_JSON), "arquivo ausente"))

    pyproj_ver = None
    if PYPROJECT.is_file():
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"))
        pyproj_ver = m.group(1) if m else None
        if pyproj_ver is None:
            v.append(Violation("R4-version-sync", ctx.rel(PYPROJECT), "sem campo version"))
    else:
        v.append(Violation("R4-version-sync", ctx.rel(PYPROJECT), "arquivo ausente"))

    for label, ver, path in (("plugin.json", plugin_ver, PLUGIN_JSON),
                             ("pyproject.toml", pyproj_ver, PYPROJECT)):
        if ver is not None and not SEMVER_RE.match(ver):
            v.append(Violation("R4-version-sync", ctx.rel(path),
                               f"versão '{ver}' não é semver MAJOR.MINOR.PATCH"))

    if plugin_ver is not None and pyproj_ver is not None and plugin_ver != pyproj_ver:
        v.append(Violation("R4-version-sync", ctx.rel(PYPROJECT),
                           f"versão {pyproj_ver} != plugin.json {plugin_ver}"))

    return v


# --- R5: ancoragem do agente (prompt de sistema + Livros-base) ---------------

MIN_PROMPT_CHARS = 200
LIVROS_RE = re.compile(r"\*\*Livros-base:\*\*")


@rule("R5-agent-anchor", "agente tem prompt de sistema e linha **Livros-base:**")
def check_agent_anchor(ctx: Context) -> List[Violation]:
    v: List[Violation] = []
    for path in ctx.agent_files:
        rel = ctx.rel(path)
        _fm, body = split_frontmatter(path.read_text(encoding="utf-8"))

        if not LIVROS_RE.search(body):
            v.append(Violation("R5-agent-anchor", rel, "sem linha **Livros-base:**"))

        # Prompt = corpo antes da linha Livros-base; precisa ser substancial.
        prompt = LIVROS_RE.split(body)[0].strip()
        if len(prompt) < MIN_PROMPT_CHARS:
            v.append(Violation("R5-agent-anchor", rel,
                               f"prompt de sistema muito curto ({len(prompt)} < {MIN_PROMPT_CHARS} chars)"))
    return v


# --- runner ------------------------------------------------------------------

def run() -> List[Violation]:
    """Executa todas as regras e devolve a lista plana de violações."""
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

    print(f"Conductor validate — {len(RULES)} regra(s), {len(violations)} violação(ões)")
    for rule_id, desc, _fn in RULES:
        n = by_rule.get(rule_id, 0)
        mark = "OK  " if n == 0 else "FAIL"
        print(f"  [{mark}] {rule_id}: {desc}" + (f"  ({n})" if n else ""))

    if violations:
        print("\nViolações:")
        for vi in violations:
            print(vi)
        return 1
    print("\nTodas as invariantes passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
