# rag/ — busca semântica no acervo

Implementa o objetivo de RAG do `plano.md`: recuperar trechos dos livros do
acervo para **fundamentar** as respostas dos cargos (combate alucinação).

## Stack

- **Embeddings:** `bge-m3` (1024-d, multilíngue) servido pelo **Ollama** local
  em `http://localhost:11434`. Acesso via `urllib` (stdlib) — sem cliente extra.
- **Vector store:** **ChromaDB** persistente (cosine), em `rag/chroma/`
  (gitignored — construído localmente, não versionado).
- **Corpus:** markdown em `C:\development\to-brain` (configurável).

## Pré-requisitos

```bash
# 1. Ollama com o modelo de embeddings
ollama pull bge-m3

# 2. Dependência Python (extra opcional do projeto)
pip install -e .[rag]
```

## Uso

```bash
# Construir/atualizar o índice (idempotente; pode retomar)
python -m rag.ingest                 # acervo inteiro
python -m rag.ingest --limit 200     # amostra rápida

# Consultar
python -m rag.query "fronteiras de bounded context"
python -m rag.query -k 8 --json "circuit breaker vs bulkhead"
python -m rag.query --category 09_seguranca_e_privacidade "STRIDE"
```

Ou pelo plugin: comando `/acervo <pergunta>` (e `/conductor` usa o acervo para
ancorar cada portão).

## Configuração (variáveis de ambiente)

| Var | Default | Para quê |
|-----|---------|----------|
| `CONDUCTOR_ACERVO` | `C:\development\to-brain` | raiz do corpus markdown |
| `CONDUCTOR_CHROMA` | `rag/chroma` | onde persistir o índice |
| `CONDUCTOR_EMBED_MODEL` | `bge-m3` | modelo de embeddings no Ollama |
| `OLLAMA_HOST` | `http://localhost:11434` | endpoint do Ollama |
