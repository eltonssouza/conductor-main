# tools/

Tooling de desenvolvimento do plugin (não faz parte do runtime do plugin).

## `validate.py` — validador de invariantes

Codifica as **regras de ouro** do Conductor como verificações executáveis,
para que a fonte não saia de sincronia com o `plano.md`. Sem dependências de
terceiros (apenas stdlib).

```bash
python tools/validate.py     # sai com código 1 se alguma regra for violada
```

Também é importável:

```python
from tools.validate import run
violacoes = run()            # lista de Violation; vazia == tudo OK
```

### Regras

| ID | Invariante |
|----|------------|
| **R1-parity** | 36 agentes + 36 skills; toda skill nomeada no `plano.md` tem diretório com `SKILL.md`. |
| **R2-frontmatter** | Frontmatter YAML com `name` + `description`; `name` em kebab-case igual ao arquivo (agente) ou diretório (skill). |
| **R3-yaml-safety** | `description` entre aspas duplas, com aspas internas escapadas — evita o parser do `claude plugin validate` descartar a metadata em silêncio. |
| **R4-version-sync** | `plugin.json` e `pyproject.toml` na mesma versão semver `MAJOR.MINOR.PATCH`. |
| **R5-agent-anchor** | Cada agente tem prompt de sistema substancial + linha `**Livros-base:**`. |
| **R6-skill-structure** | Cada `SKILL.md` tem seção `Quando usar` + `Passos` numerados. |

Para adicionar uma regra: escreva uma função decorada com `@rule("ID", "descrição")`
que receba o `Context` e devolva uma lista de `Violation`.
