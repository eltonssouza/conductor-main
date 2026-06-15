# tools/

Development tooling for the plugin (not part of the plugin runtime).

## `validate.py` — invariant validator

Encodes the **golden rules** of Conductor as executable checks, so that the
source never drifts out of sync with `plano.md`. No third-party dependencies
(stdlib only).

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
| **R1-parity** | 36 agents + 36 skills, each with `SKILL.md`; `plano.md` still names 36 skills. |
| **R2-frontmatter** | YAML frontmatter with `name` + `description`; `name` in kebab-case matching the file (agent) or directory (skill). |
| **R3-yaml-safety** | `description` double-quoted with internal quotes escaped — prevents the `claude plugin validate` parser from silently discarding metadata. |
| **R4-version-sync** | `plugin.json` and `pyproject.toml` on the same `MAJOR.MINOR.PATCH` semver. |
| **R5-agent-anchor** | Each agent has a substantial system prompt + a `**Reference books:**` line. |
| **R6-skill-structure** | Each `SKILL.md` has a `When to use` section + numbered steps. |
| **R7-flow-integrity** | The `/cdt` command has all 11 flow gates and only references agents/skills/commands that exist. |

To add a rule: write a function decorated with `@rule("ID", "description")`
that takes a `Context` and returns a list of `Violation`.

## Quality gate (Gate 7)

The validator runs automatically as the plugin's quality gate:

- **CI:** [`.github/workflows/validate.yml`](../.github/workflows/validate.yml)
  runs it on every push to `main` and on pull requests (pure stdlib, no install).
- **Local (optional):** [`.pre-commit-config.yaml`](../.pre-commit-config.yaml)
  runs it before each commit once you `pip install pre-commit && pre-commit install`.
