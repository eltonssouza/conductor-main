# Guia de Início Rápido — Conductor (cdt)

Este guia é para quem nunca usou o Conductor antes.
Você vai sair do zero até rodar a sua primeira feature em 6 passos.

---

## O que é o Conductor?

O Conductor é uma ferramenta de linha de comando que turbina o seu assistente de IA (Claude Code, por exemplo) com duas coisas:

1. **Uma biblioteca de boas práticas** (livros de referência de engenharia de software indexados para busca semântica — você pergunta em linguagem natural, ele busca o trecho relevante)
2. **Um diário de projeto** (registro das decisões, erros e soluções do seu projeto — o assistente lembra o que já foi discutido)

Você instala o `cdt` na sua máquina uma vez, depois "enrola" cada projeto que quiser usar com ele. Depois disso, dentro do Claude Code, um comando `/cdt` aparece para você guiar suas features por um fluxo de 11 etapas com aprovação a cada passo.

---

## Pré-requisitos

- **Python 3.10+** instalado
- **Docker** instalado e em execução (para a biblioteca e o diário rodarem)
- **Claude Code** instalado (é o editor/assistente onde o `/cdt` vai aparecer)

---

## Passo 1 — Instalar o Conductor

Escolha **uma** das opções abaixo:

### Opção A — via pipx (recomendado)

`pipx` instala ferramentas de linha de comando Python em ambientes isolados, sem conflitar com outros pacotes do sistema.

```bash
# 1. Instalar o pipx (se ainda não tiver)
pip install pipx
python -m pipx ensurepath

# 2. Feche e reabra o terminal para o PATH atualizar

# 3. Instalar o Conductor
pipx install conductor
```

### Opção B — via uv (se já tiver uv instalado)

```bash
uv tool install conductor
```

### Opção C — via script (one-liner)

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.ps1 | iex
```

Para confirmar que funcionou:

```bash
cdt --help
```

> `cdt` e `conductor` são a mesma coisa — ambos funcionam.

---

## Passo 2 — Subir a biblioteca (Docker, uma vez por máquina)

O Conductor precisa de dois serviços rodando em Docker para funcionar:

- **RAG** (ChromaDB + Ollama): guarda e busca os livros de referência
- **Honcho**: guarda o diário de cada projeto

```bash
# 1. Sobe a biblioteca de boas práticas
cdt up

# 2. Confirma o que foi indexado
cdt library status

# 3. Configura o diário (escolha um provedor de IA para ele raciocinar)
cdt honcho setup

# 4. Sobe o backend do diário
cdt honcho up
```

No passo 3, o `honcho setup` vai mostrar um menu. Se você não quiser usar uma chave de API paga, escolha `ollama` (roda local, gratuito). Como o Ollama roda **em Docker** (container `conductor-ollama-1`, subido pelo `cdt up`), o modelo precisa ser baixado **dentro do container** antes:

```bash
# 1. Baixe o modelo DENTRO do container do Ollama
docker exec conductor-ollama-1 ollama pull qwen2.5:3b

# 2. Aponte o Honcho pra ele
cdt honcho setup --provider ollama --model qwen2.5:3b
```

Provedores disponíveis: `openai | deepseek | openrouter | anthropic | ollama | custom`

> **Trocando de provedor depois?** Se o `.env` do diário já existe, acrescente `--force` (veja as Dúvidas frequentes).

---

## Passo 3 — Escolher as linguagens da sua biblioteca (opcional, mas recomendado)

Por padrão, só o conteúdo agnóstico de linguagem (boas práticas gerais) é indexado.
Para adicionar livros específicos de Java, Python, Angular, etc.:

```bash
# Abre um menu interativo — escolha por número, separados por vírgula
cdt library stacks

# Só para ver o que está disponível sem alterar nada
cdt library stacks --list
```

No menu interativo, você digita os números das stacks que quer. Por exemplo: `3, angular@21` adiciona Java + Angular versão 21.

Depois de escolher, rode `cdt up` novamente para indexar os novos livros:

```bash
cdt up
```

### Atualizar depois que o conteúdo da biblioteca melhorar

O stack Docker busca os livros do repositório da biblioteca (`CONDUCTOR_LIBRARY_REPO@REF`), **não** do disco local — então, se você melhorou o conteúdo e enviou (push) para esse repositório, `cdt up` sozinho não vê a mudança (ele pula o download quando a biblioteca já está preenchida). Force um novo download + reindexação:

```bash
cdt library update             # rebaixa o repositório e reindexa só os trechos que mudaram
cdt library update --rebuild   # também zera o índice antes (limpa chunks de livros removidos/renomeados)
```

O `update` re-executa apenas o serviço de ingestão; o Ollama e o ChromaDB continuam de pé e o modelo bge-m3 nunca é rebaixado (mesmo com `--rebuild`).

---

## Passo 4 — Enrolar o seu projeto

Navegue até a pasta do projeto e rode o init:

```bash
cd /caminho/do/seu/projeto
cdt init
```

Isso cria dentro do projeto:

- `.claude/` — agentes e skills configurados para o seu tipo de projeto
- `.cdt/` — configuração e diário local
- `CLAUDE.md` — guia de contexto que o Claude Code vai ler automaticamente

Quer ver o que o Conductor detectou no seu projeto antes de iniciar?

```bash
cdt detect
```

Se você usa mais de um assistente de IA (Claude Code, OpenCode, Codex, Pi), pode gerar a configuração para todos de uma vez:

```bash
cdt init --target all
```

Por padrão o target é `claude`.

---

## Passo 5 — Recarregar o Claude Code

Feche e reabra o Claude Code na pasta do projeto.
Isso é necessário para que o comando `/cdt` e os hooks apareçam.

---

## Passo 6 — Rodar a sua primeira feature

Dentro do Claude Code, digite:

```
/cdt implement <descreva sua feature aqui>
```

O fluxo vai parar e pedir sua aprovação a cada uma das 11 etapas antes de seguir. Você está no controle — nada avança sem o seu OK.

---

## Alternativa — usar o Conductor com o Odysseus (opcional)

Os passos 4 a 6 acima assumem o **Claude Code** (ou OpenCode/Codex/Pi) como harness. Se você usa o **[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus)** — um workspace de IA self-hosted em Docker, útil pra quem roda LLMs sem um harness maduro (DeepSeek, Qwen, GLM…) — o Conductor integra com ele de um jeito **diferente**:

> ⚠️ **A integração com Odysseus é GLOBAL, feita uma única vez — NÃO use `cdt init`.**
> O `cdt init` é por projeto (Claude/OpenCode/Codex/Pi). O Odysseus recebe **todas** as skills de uma vez no "Brain", e nunca é tocado por `init`/`sync`.

### Pré-requisitos

- **Odysseus já instalado** e rodando em Docker na sua máquina.
- **`cdt up` rodando** — o Odysseus usa o mesmo backend RAG (biblioteca) do Conductor.

### Passo único — instalar o Conductor no Brain do Odysseus

Se o Odysseus está rodando em **Docker**, o Conductor **auto-detecta** a pasta de instalação dele (pelo container) — você pode rodar de qualquer lugar. Caso contrário, rode de dentro da pasta do Odysseus, defina `ODYSSEUS_HOME`, ou aponte com `--home`. Passe as pastas do host que o agente vai poder acessar:

```bash
# Instala TODAS as skills (36 roles + /cdt + /cdt-intake) no Brain do Odysseus
# e libera o acesso do agente às suas pastas de projeto
cdt odysseus install --projects C:\caminho\para\seus\projetos
```

Isso faz duas coisas, sem nunca modificar o Odysseus em si:

1. Grava as skills do Conductor no Brain (`data/skills/conductor/`), formatadas para o Odysseus as exibir.
2. Dá ao agente acesso às pastas do host via um `docker-compose.override.yml` (bind-mount) + um patch em `tool_path_extra_roots`.

Depois disso, dentro do Odysseus, as skills do Conductor (`/cdt`, `/cdt-intake`, os 36 papéis) ficam disponíveis.

### Opcional — expor as memórias via MCP

Para o agente do Odysseus consultar a biblioteca e o diário ao vivo, suba o servidor MCP do Conductor e registre-o:

```bash
# 1. Sobe o servidor MCP do Conductor (biblioteca + diário) em http://<host>:8808/mcp
cd infra/mcp && docker compose up -d --build

# 2. Registra esse MCP no Odysseus durante o install
cdt odysseus install --projects C:\caminho\para\seus\projetos --with-mcp
```

### Conferir a instalação

```bash
cdt odysseus doctor   # re-checa skills no Brain, acesso às pastas e o registro MCP
```

---

## Atualizando o Conductor

O método de atualização depende de como você instalou:

### Instalação via script (padrão para a maioria dos usuários)

Se você instalou com o one-liner de instalação (curl/irm), use:

```bash
cdt update
```

Isso faz um `git pull --ff-only` no repositório do Conductor. O código já está ativo imediatamente — não precisa reinstalar.

Se o `pyproject.toml` mudou (novas dependências foram adicionadas na versão nova), use:

```bash
cdt update --reinstall
```

Isso puxa o código novo **e** reinstala as dependências (`pip install -e ".[rag,honcho]"`).

### Instalação via pipx

```bash
pipx upgrade conductor
```

### Instalação via uv

```bash
uv tool upgrade conductor
```

### Instalação via pip (fonte)

```bash
pip install --upgrade --force-reinstall "git+https://github.com/eltonssouza/conductor-main.git"
```

### Após atualizar: sincronizar os projetos enrolados

Quando o Conductor traz novos templates de agentes, skills ou automações, você precisa propagá-los para cada projeto que já estava enrolado:

```bash
cd /caminho/do/seu/projeto
cdt sync
```

> Faça isso em cada projeto após um `cdt update` que tenha introduzido mudanças nos templates (o changelog vai indicar quando isso é necessário).

---

## Comandos do dia a dia

### Pesquisar a biblioteca de boas práticas

```bash
cdt library "como definir limites de bounded context?"
cdt library "circuit breaker vs bulkhead"
```

Retorna trechos relevantes dos livros de referência indexados.

### Consultar o diário do projeto

```bash
# Busca semântica: o que já foi decidido sobre X?
cdt journal recall "por que escolhemos arquitetura hexagonal?"

# Lista erros e soluções já registrados
cdt journal log --kind error,solution

# Adiciona uma entrada manualmente ao diário
cdt journal add --kind decision "escolhemos PostgreSQL por já termos expertise no time"
```

Tipos de entrada disponíveis: `reasoning | decision | plan | error | solution | checkpoint`

### Ver e gerenciar projetos enrolados

```bash
# Lista todos os projetos que você já rodou `cdt init`
cdt list
```

### Atualizar a configuração de um projeto existente

Se você atualizou o Conductor e quer que o projeto reflita as novidades:

```bash
cd /caminho/do/projeto
cdt sync
```

### Ver status da biblioteca

```bash
cdt library status   # livros indexados, categorias, contagem de chunks
```

---

## Referência rápida de todos os comandos

| Comando                                   | O que faz                                                                                                      |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `cdt init`                              | Enrola um projeto (gera`.claude/`, `.cdt/`, `CLAUDE.md`)                                                 |
| `cdt sync`                              | Atualiza a config de um projeto já enrolado                                                                   |
| `cdt detect`                            | Mostra o que o Conductor detecta no projeto atual                                                              |
| `cdt list`                              | Lista todos os projetos enrolados                                                                              |
| `cdt up`                                | Sobe os containers Docker (biblioteca + embeddings)                                                            |
| `cdt down`                              | Para os containers Docker                                                                                      |
| `cdt ingest`                            | Reindexar os livros da biblioteca manualmente                                                                  |
| `cdt library "<pergunta>"`              | Busca semântica nos livros de referência                                                                     |
| `cdt library status`                    | Mostra o que está indexado                                                                                    |
| `cdt library stacks`                    | Menu para escolher linguagens/frameworks                                                                       |
| `cdt library stacks --list`             | Lista stacks disponíveis e selecionadas                                                                       |
| `cdt library reindex`                   | Indexa arquivos novos ainda não no ChromaDB                                                                   |
| `cdt library update [--rebuild]`        | Rebaixa o repositório da biblioteca e reindexa (após melhorar o conteúdo); `--rebuild` zera o índice          |
| `cdt library add <arquivo.md>`          | Adiciona um arquivo específico ao índice                                                                     |
| `cdt journal add`                       | Adiciona entrada ao diário do projeto                                                                         |
| `cdt journal recall "<pergunta>"`       | Busca semântica no diário                                                                                    |
| `cdt journal log`                       | Lista entradas do diário (suporta`--kind`)                                                                  |
| `cdt honcho setup`                      | Configura o provedor de IA do diário                                                                          |
| `cdt honcho up`                         | Sobe o backend Honcho (diário)                                                                                |
| `cdt honcho down`                       | Para o backend Honcho                                                                                          |
| `cdt update`                            | Atualiza o Conductor (git pull);`--reinstall` também reinstala dependências                                |
| `cdt mcp`                               | Roda as memórias como servidor MCP (stdio)                                                                    |
| `cdt odysseus install --projects <dir>` | Instala todas as skills no Brain do Odysseus + libera acesso às pastas (global;`--with-mcp` registra o MCP) |
| `cdt odysseus doctor`                   | Re-checa uma instalação do Odysseus                                                                          |
| `cdt quickstart`                        | Imprime este fluxo resumido no terminal                                                                        |
| `cdt --help`                            | Mostra a ajuda completa                                                                                        |

---

## Dúvidas frequentes

**O `/cdt` não aparece no Claude Code.**
Feche e reabra o Claude Code na pasta do projeto. Se ainda não aparecer, rode `cdt init` novamente.

**Erro de conexão ao rodar `cdt library` ou `cdt journal recall`.**
Os containers precisam estar rodando. Rode `cdt up` e `cdt honcho up` primeiro.

**Quero trocar o provedor do diário (ex.: DeepSeek → Ollama).**
O `.env` já existe, então o `cdt honcho setup` se recusa a sobrescrever sem `--force` (mensagem: `... .env exists (use --force to overwrite)`). Para Ollama, baixe o modelo no container antes:

```bash
docker exec conductor-ollama-1 ollama pull qwen2.5:3b
cdt honcho setup --provider ollama --model qwen2.5:3b --force
cdt honcho down && cdt honcho up
```

Trocar entre provedores que usam o mesmo embedding (`bge-m3`) **não apaga o diário** — não precisa recriar volume.

**Quero recomeçar a biblioteca do zero.**

```bash
cdt down
docker volume rm conductor_chroma
cdt up
```

**Como vejo os logs dos containers?**
Use `docker logs <nome-do-container>` ou `docker compose logs` na pasta `infra/` do Conductor.
