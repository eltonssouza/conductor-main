---
description: "Busca semântica no acervo (RAG): recupera os trechos mais relevantes dos livros de referência via bge-m3 + ChromaDB para fundamentar uma resposta e reduzir alucinação."
argument-hint: "[pergunta a consultar no acervo]"
---

# /acervo — fundamentação no acervo (RAG)

Recupera trechos relevantes dos livros do acervo para **ancorar** a resposta nas
fontes, em vez de confiar só na memória do modelo (mitiga alucinação — princípio
do agente `ai-engineer`).

Pergunta: **$ARGUMENTS**

## Passos

1. Execute a busca semântica (top-k, saída JSON):

   ```bash
   python -m rag.query --json -k 6 "$ARGUMENTS"
   ```

2. Se vier `ERRO na busca`, diagnostique: o índice pode não estar construído
   (`python -m rag.ingest`) ou o Ollama/bge-m3 pode estar fora do ar.

3. Leia os trechos retornados (`source`, `section`, `text`) e **fundamente a
   resposta neles**, citando o livro e a seção de cada afirmação relevante.

4. Para focar uma área, filtre por categoria do acervo:

   ```bash
   python -m rag.query --json -k 6 --category 09_seguranca_e_privacidade "$ARGUMENTS"
   ```

5. Se nenhum trecho for pertinente, **diga isso** — não invente fonte. Distinga o
   que veio do acervo do que é raciocínio próprio.
