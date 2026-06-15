# infra/honcho — self-hosted Honcho (development diary backend)

[Honcho](https://honcho.dev) is the long-term memory behind Conductor's
`/journal` diary. It stores the diary messages and reasons over them in the
background (peer modeling + dialectic), so `recall` answers by meaning. This
compose runs it locally; the diary's local JSONL mirror works without it, so
Honcho is **optional** — it adds intelligent recall on top.

## Bring it up

```bash
# 1. Choose the reasoning provider (writes .env for it)
conductor honcho-setup                # interactive: openai | deepseek | openrouter | ollama | anthropic
#   or non-interactive, e.g.:  conductor honcho-setup --provider ollama
#   or manual:                 cp .env.example .env  (uncomment one preset)

# 2. Start it
docker compose up -d          # first run clones + builds Honcho (a few minutes)
docker compose ps             # api / deriver / database / redis healthy
curl http://localhost:8000/health
```

Then install the SDK and point the diary at it:

```bash
pip install -e .[honcho]      # from the repo root
# default base_url is http://localhost:8000 (override: CONDUCTOR_HONCHO_URL)
conductor journal recall "why did we choose this architecture?"
```

## Reasoning engine — your choice

The `deriver`, `dialectic`, and `summary` features run on **whichever provider
you pick at install time** — nothing is pre-selected. `conductor honcho-setup`
ships presets for **OpenAI, DeepSeek, OpenRouter, local Ollama, and Anthropic**,
and any OpenAI-compatible endpoint (Together, Fireworks, vLLM…) works too. It all
maps to the `*_MODEL_CONFIG__*` vars in `.env`; re-run the setup to switch.

## Services

| Service | Image | Port (localhost only) |
|---------|-------|-----------------------|
| api | built from upstream Honcho | 8000 |
| deriver | same image, background worker | — |
| database | `pgvector/pgvector:pg15` | 5432 |
| redis | `redis:8.2` | 6379 |

All ports bind to `127.0.0.1` — nothing is exposed off the host.

## Version pinning (caveat)

The api/deriver image builds from the upstream repo at `main`. For a
reproducible build, pin a tag/SHA:

```bash
HONCHO_REF=v2.4.0 docker compose build      # then `up -d`
```

If an upstream change breaks the build, pin a known-good `HONCHO_REF`.
