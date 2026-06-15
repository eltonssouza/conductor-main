# infra/honcho — self-hosted Honcho (development diary backend)

[Honcho](https://honcho.dev) is the long-term memory behind Conductor's
`journal` diary. It stores the diary messages and reasons over them in the
background (peer modeling + dialectic), so `conductor journal recall` answers by
meaning. The diary's local JSONL mirror works without it, so Honcho is
**optional** — it adds intelligent recall on top.

## Bring it up

```bash
# 1. SDK + reasoning provider
pip install -e .[honcho]                 # from the repo root
conductor honcho-setup --provider deepseek --api-key sk-...   # or: ollama (local)

# 2. Clone Honcho locally (the git-URL build context fails on Docker Desktop /
#    Windows, so we build from a local clone)
git clone https://github.com/plastic-labs/honcho.git C:/path/to/honcho-src

# 3. Start it (point HONCHO_SRC at the clone)
cd conductor/infra/honcho
HONCHO_SRC=C:/path/to/honcho-src docker compose up -d
```

If the **api** container crashes on startup with a *dimension mismatch* (the
schema is created at 1536 but local embeddings are 1024-d), run Honcho's
reconfigure script once against the running DB, then bring the stack up again:

```bash
HONCHO_SRC=... docker compose run --rm --no-deps \
  --entrypoint /app/.venv/bin/python deriver scripts/configure_embeddings.py --yes
HONCHO_SRC=... docker compose up -d
curl http://localhost:8000/health        # {"status":"ok"}
```

Then the diary syncs + recalls by meaning:

```bash
conductor journal add --gate 4 --kind decision "chose hexagonal arch; ADR-1"
conductor journal recall "why this architecture?"
```

## Reasoning engine — your choice (recommended: DeepSeek)

`conductor honcho-setup` writes the full config Honcho needs:

- **Reasoning** (deriver + dialectic + summary): the chosen provider's model.
  The dialectic uses per-level configs (`DIALECTIC_LEVELS__<level>__MODEL_CONFIG`),
  which the setup overrides — otherwise Honcho's own default model is sent to your
  provider and rejected.
- **Global base URL** (`LLM_OPENAI_BASE_URL`) so calls without a per-feature
  override hit your provider, not OpenAI.
- **Embeddings**: DeepSeek/Anthropic/OpenRouter have no compatible embeddings, so
  embeddings default to the **local Ollama bge-m3** (1024-d) — a free, local
  hybrid alongside cloud reasoning. (OpenAI uses its own 1536-d embeddings.)

Presets: `openai | deepseek | openrouter | ollama | anthropic`. Re-run to switch.

## Services (all bound to 127.0.0.1)

| Service | Image | Host port |
|---------|-------|-----------|
| api | built from the local Honcho clone | 8000 |
| deriver | same image, background worker | — |
| database | `pgvector/pgvector:pg15` | — (internal) |
| redis | `redis:8.2` | — (internal) |

database/redis are internal-only (no host bind) to avoid clashing with a host
Postgres/Redis on 5432/6379.

## Notes

- Windows clones may give the Honcho shell scripts CRLF endings, which break the
  container entrypoint (`set: Illegal option`). Strip them:
  `find <clone> -name '*.sh' -exec sed -i 's/\r$//' {} +`.
- `conductor honcho-setup` writes the `.env` here (gitignored). Never commit it.
