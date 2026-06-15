# tools/

Development tooling (not shipped with the CLI).

## `validate.py` — invariant validator

Encodes the **golden rules** over Conductor's role **templates**
(`conductor/templates/`) as executable checks, so the source never drifts. No
third-party dependencies (stdlib only).

```bash
python tools/validate.py     # exits with code 1 if any rule is violated
```

Also importable:

```python
from tools.validate import run
violations = run()            # list of Violation; empty == all OK
```

### Rules

| ID | Invariant |
|----|-----------|
| **R1-parity** | 36 agent templates + 36 skill templates, each with `SKILL.md`. |
| **R2-frontmatter** | YAML frontmatter with `name` + `description`; `name` in kebab-case matching the file (agent) or directory (skill). |
| **R3-yaml-safety** | `description` double-quoted with internal quotes escaped — keeps the scaffolded `.claude/` frontmatter parseable. |
| **R4-version** | `pyproject.toml` has a valid `MAJOR.MINOR.PATCH` semver. |
| **R5-agent-anchor** | Each agent has a substantial system prompt + a `**Reference books:**` line. |
| **R6-skill-structure** | Each `SKILL.md` has a `When to use` section + numbered steps. |
| **R7-roles-flow** | `conductor/roles.py` has 36 roles, each resolving 1:1 to an existing agent + skill template; `templates/flow.md` has all 11 gates. |
| **R8-agent-model** | Each agent declares a `model:` tier — one of `opus`, `sonnet`, `haiku` — so the generated subagents never fall back silently on a typo'd alias. |

To add a rule: write a function decorated with `@rule("ID", "description")`
that takes a `Context` and returns a list of `Violation`.

## Quality gate

The validator runs automatically as the project's quality gate:

- **CI:** [`.github/workflows/validate.yml`](../.github/workflows/validate.yml)
  runs it on every push to `main` and on pull requests (pure stdlib, no install).
- **Local (optional):** [`.pre-commit-config.yaml`](../.pre-commit-config.yaml)
  runs it before each commit once you `pip install pre-commit && pre-commit install`.
