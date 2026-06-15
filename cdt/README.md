# cdt/ — per-project enrollment + development diary

Makes Conductor **per-project** (not just global) and gives each enrolled
project a **long-term memory**. Two complementary memories ground the 36 roles:

| Memory | What | Backed by |
|--------|------|-----------|
| **Library (RAG)** | what good practice says (static books) | `rag/` + ChromaDB + bge-m3 |
| **Diary (Honcho)** | what *this* project decided & learned (dynamic) | `cdt/` + Honcho + local JSONL |

## Enroll a project — `cdt init`

```bash
python -m cdt.init                 # enroll the cwd
python -m cdt.init path/to/proj    # enroll another dir
python -m cdt.init --type backend --force
```

Creates `.cdt/` in the project:

```
.cdt/
  config.json        # project slug, type, Honcho workspace, created date
  stack/<TYPE>.md    # detected technologies -> makes RAG queries project-aware
  journal/*.jsonl    # local diary mirror (gitignored by .cdt/.gitignore)
```

`<TYPE>` ∈ `backend | frontend | mobile | fullstack | library | data | unknown`,
detected from manifests (Angular/React/Vue/Next, Maven/Gradle/Go/Python/.NET/
Rust, Flutter/RN/Xcode…). Enrolled projects are tracked in the global registry
`~/.claude/conductor/projects.json` (override with `CONDUCTOR_HOME`).

Via the plugin: **`/cdt init`** runs this and finalizes the stack file.

## Development diary — `/journal`

```bash
python -m cdt.journal add --gate 4 --kind decision "chose hexagonal arch; ADR-1"
python -m cdt.journal add --owner  --kind plan     "MVP first; auth phase 2"
python -m cdt.journal recall "why this architecture?"
python -m cdt.journal log
```

`--kind` ∈ `reasoning | decision | plan | error | solution`. Every entry is
written to the **local JSONL mirror first** (works offline), then best-effort
synced to Honcho. `recall` queries Honcho's background reasoning; if Honcho is
down it falls back to a keyword scan of the mirror.

## Honcho backend (optional)

The diary works without Honcho (local mirror only). For meaning-based recall,
run the self-hosted server and install the SDK:

```bash
cd infra/honcho && cp .env.example .env   # set the DeepSeek key
docker compose up -d
pip install -e .[honcho]
```

Peer model: two peers per workspace — `conductor` (all AI roles) and `owner`
(the human). Workspace id = the project slug, so history is **isolated per
project**.

## Configuration (environment variables)

| Var | Default | Purpose |
|-----|---------|---------|
| `CONDUCTOR_HOME` | `~/.claude/conductor` | global registry location |
| `CONDUCTOR_HONCHO_URL` | `http://localhost:8000` | Honcho server (overrides config) |
| `CONDUCTOR_HONCHO_API_KEY` | `local` | Honcho API key (self-host: any value) |
