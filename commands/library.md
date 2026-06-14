---
description: "Semantic search over the library (RAG): retrieves the most relevant passages from the reference books via bge-m3 + ChromaDB to ground an answer and reduce hallucination."
argument-hint: "[question to search in the library]"
---

# /library — grounding in the library (RAG)

Retrieves relevant passages from the library's books to **anchor** the answer in
sources, instead of relying on the model's memory alone (mitigates hallucination
— principle of the `ai-engineer` agent).

Question: **$ARGUMENTS**

## Steps

1. Run the semantic search (top-k, JSON output):

   ```bash
   python -m rag.query --json -k 6 "$ARGUMENTS"
   ```

2. If it returns `Search failed:`, diagnose: the index may not be built
   (`python -m rag.ingest`) or Ollama/bge-m3 may be down.

3. Read the returned passages (`source`, `section`, `text`) and **ground the
   answer in them**, citing the book and section for each relevant claim.

4. To focus on an area, filter by library category:

   ```bash
   python -m rag.query --json -k 6 --category 09_seguranca_e_privacidade "$ARGUMENTS"
   ```

5. If no passage is relevant, **say so** — do not invent a source. Distinguish
   what came from the library from your own reasoning.
