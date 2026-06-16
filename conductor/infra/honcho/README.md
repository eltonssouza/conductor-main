# infra/honcho — self-hosted Honcho (development diary backend)

[Honcho](https://honcho.dev) is the long-term memory behind Conductor's
`journal` diary. It stores the diary messages and reasons over them in the
background (peer modeling + dialectic), so `conductor journal recall` answers by
meaning. The diary's local JSONL mirror works without it, so Honcho is
**optional** — it adds intelligent recall on top.

## Bring it up — one command

```bash
pip install -e .[honcho]                       # SDK
conductor honcho setup --provider deepseek     # key auto-read (see below); or --api-key sk-...
conductor honcho up                            # clone + build + start
```

For DeepSeek, the key is read from `C:\honcho\deep-seek-key.txt` (line
`API-KEY-DEEP_SEEK: "sk-..."`) when `--api-key` is omitted; override the path
with `CONDUCTOR_DEEPSEEK_KEY_FILE`.

`conductor honcho up` does everything the stack needs automatically: clones
Honcho if missing, strips the Windows CRLF endings that break the entrypoint,
builds from the local clone (the git-URL build context fails on Docker Desktop),
brings the stack up, and — on the first run — reconfigures the DB vector
dimension to 1024 (for the local bge-m3 embeddings) when it detects the
mismatch. `conductor honcho down` stops it.

> Run `conductor up` too: Honcho embeds messages via the local bge-m3, which the
> RAG stack's Ollama serves.

Manual equivalent (if you prefer): `git clone` Honcho, `HONCHO_SRC=... docker
compose up -d` in this dir, and run `scripts/configure_embeddings.py --yes` once
if the api reports a dimension mismatch.

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
