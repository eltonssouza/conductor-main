# Conductor

Conductor is a **global command-line tool** that turns any software project into a
**Claude-Code-conducted** project. You run one command inside a project and
Conductor scaffolds Claude-Code-native configuration into it: a relevant subset of
**36 industry role Agents + Skills** under `.claude/`, the project's detected
**tech stack**, and a generated **`CLAUDE.md`** that describes those roles and an
**11-gate development flow** (discovery → spec → security → architecture → test →
code → quality gate → validation → delivery → observability → learning).

Conductor is **not a Claude Code plugin**. It is the tool that *prepares* a
project. The actual reasoning happens in **your** Claude (Claude Code), driven by
the project-local `.claude/` and `CLAUDE.md` that Conductor writes. Two long-term
memories ground every decision:

| Memory | What it knows | Backed by |
|--------|---------------|-----------|
| **Library (RAG)** | what good engineering practice says — a static corpus of reference books | `cdt library` → bge-m3 + ChromaDB (Docker) |
| **Diary (Honcho)** | what *this* project decided and learned over time | `cdt journal` → Honcho (Docker) + a local memory tree |

The work is driven by the **`/cdt` slash command**, an interactive control loop
that walks a demand through the gates and **stops for your approval at each one**.
The diary is **live memory**: Claude Code hooks installed by Conductor capture
your prompts and inject what Honcho remembers back into each new session, so the
project's memory grows as you work and follows you across sessions.

---

## Quickstart

From install to your first feature (also printed by `cdt quickstart`):

```bash
# 1. Install (once)
pipx install conductor                 # or, from a clone: pip install -e .[rag,honcho]

# 2. Start the two memories in Docker (once per machine)
cdt up                                 # RAG stack: Ollama + ChromaDB + ingest the books
cdt honcho setup --provider deepseek   # configure the diary's reasoning (first time only)
cdt honcho up                          # the Honcho diary backend

# 3. Enroll your project
cd /path/to/your-project
cdt init                               # scaffold .claude/ + .cdt/ + CLAUDE.md + /cdt + hooks

# 4. Reload Claude Code in that project  -> so the /cdt command and the hooks load

# 5. Drive your first feature through the gates (inside Claude Code)
/cdt implement <your feature>          # interactive: stops for your approval at each gate
```

Handy along the way:

```bash
cdt library "<question>"               # ground an answer in the reference books
cdt journal recall "<question>"        # recall what this project already decided
cdt journal log --kind error,solution  # list problems already solved
cdt sync                               # after upgrading Conductor: refresh an enrolled project
cdt viewer                             # 3D map of the library + add a book from the browser
```

> **Upgrading?** After updating Conductor, run `cdt sync` in each enrolled
> project so it receives new features (the `/cdt` driver, the hooks, the memory
> tree). A project enrolled by an older version won't have `/cdt` until you sync.

---

## Table of contents

1. [Quickstart](#quickstart)
1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [The Docker backends](#the-docker-backends)
   - [RAG stack — `cdt up`](#rag-stack--cdt-up)
   - [Diary backend (Honcho) — `cdt honcho up`](#diary-backend-honcho--cdt-honcho-up)
   - [Where to put the DeepSeek API key](#where-to-put-the-deepseek-api-key)
5. [Using Conductor in a project](#using-conductor-in-a-project)
   - [`cdt init`](#cdt-init)
   - [`cdt sync` — the living CLAUDE.md](#cdt-sync--the-living-claudemd)
6. [The 11-gate flow](#the-11-gate-flow)
7. [The library (Chroma) — grounding answers](#the-library-chroma--grounding-answers)
8. [The 3D viewer & screen ingest](#the-3d-viewer--screen-ingest)
9. [The diary (Honcho) — project memory](#the-diary-honcho--project-memory)
10. [CLI reference](#cli-reference)
11. [Configuration (environment variables)](#configuration-environment-variables)
12. [Repository layout](#repository-layout)
13. [Invariants / quality gate](#invariants--quality-gate)
14. [Troubleshooting](#troubleshooting)
15. [Security notes](#security-notes)

---

## How it works

```
                ┌─────────────────────────────────────────────────────┐
                │  cdt  (global CLI, installed with pipx/pip)          │
                └─────────────────────────────────────────────────────┘
                      │                    │                    │
        cdt init        cdt library    cdt journal
                      │                    │                    │
                      ▼                    ▼                    ▼
        Generates into the          Queries the RAG      Records / recalls
        target project:             stack (Chroma +      project decisions
          .claude/agents+skills     bge-m3 on GPU)       (Honcho + local
          .cdt/ (stack, diary)             │             JSONL mirror)
          CLAUDE.md (the flow)             │                    │
                      │                    └──────┬─────────────┘
                      ▼                           ▼
            Open the project in Claude Code. The project-scoped `.claude/`
            agents/skills load automatically (no plugin). CLAUDE.md becomes
            project context, and the agents ground every gate in the two memories.
```

The reasoning is done by Claude Code reading the generated `.claude/` and
`CLAUDE.md`. Conductor itself contains **no LLM** — it scaffolds, indexes, and
remembers. Each generated agent declares a `model:` tier (`opus` for
architecture/security/strategy, `sonnet` for implementation, `haiku` for light
facilitation), so Claude Code runs each role on a right-sized model.

---

## Requirements

- **Python 3.9+** (the CLI is pure standard library; the RAG/diary extras pull in
  `chromadb` / `honcho-ai`).
- **Docker + Docker Compose** — for the RAG stack and the Honcho diary backend.
- **Git** — Conductor's Docker images are built from local source / a local clone.
- **An NVIDIA GPU + the NVIDIA Container Toolkit** *(recommended, optional)* — so
  the `bge-m3` embedding model runs on the GPU. Without it the first full ingest of
  the corpus takes hours on CPU.
- **A DeepSeek API key** *(recommended for the diary)* — powers Honcho's
  intelligent recall. The local-Ollama option works without any key but the small
  local model gives weaker results. See
  [Where to put the DeepSeek API key](#where-to-put-the-deepseek-api-key).
- **The reference-book corpus** — the markdown books the RAG indexes. `cdt up`
  fetches them automatically from the public library repo
  ([`eltonssouza/conductor-library`](https://github.com/eltonssouza/conductor-library));
  nothing to download by hand. Point it at a fork/branch with
  `CONDUCTOR_LIBRARY_REPO` / `CONDUCTOR_LIBRARY_REF`.

---

## Installation

One line. The installer checks prerequisites, installs [uv](https://astral.sh/uv)
(isolated, no sudo), clones Conductor into `~/.conductor/src`, and installs the
`cdt` / `conductor` commands as an editable tool — so the Docker backends work
too. Re-run any time to update.

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.ps1 | iex
```

Knobs (env vars): `CONDUCTOR_REF` (branch/tag), `CONDUCTOR_SRC` (clone dir),
`CONDUCTOR_EXTRAS` (default `rag,honcho`; set `none` for a core-only install),
`CONDUCTOR_DRY_RUN=1` (preview without changing anything), `NO_COLOR=1`.

Preview the Windows install in a throwaway sandbox first (nothing touches your
PATH or `~/.conductor`): `powershell -ExecutionPolicy Bypass -File tools/simulate-install.ps1 -Init`.

<details>
<summary>Manual install (from a clone)</summary>

The Docker backends are built from source, so a clone is needed to run them:

```bash
git clone https://github.com/eltonssouza/conductor-main.git
cd conductor-main
uv tool install --editable ".[rag,honcho]"   # or: pipx install --editable ".[rag,honcho]"
```

`[rag]` adds the ChromaDB client + scikit-learn/numpy (`cdt library`, `cdt viewer`);
`[honcho]` adds the Honcho SDK (`cdt journal recall`). Omit them for a core-only CLI.
</details>

This gives you the `cdt` command (with `conductor` kept as an alias). Verify:

```bash
cdt --help
```

---

## The Docker backends

Conductor's two long-term memories run in Docker. Each is a single command.

### RAG stack — `cdt up`

Builds and starts the library RAG: **Ollama** (serving the `bge-m3` embedding
model), **ChromaDB** (the vector store), and a one-shot **conductor** service that
fetches the books, pulls the model, and ingests everything.

```bash
# The book corpus is fetched from the public library repo automatically —
# nothing local to place. (Override with CONDUCTOR_LIBRARY_REPO / _REF.)
cdt up                    # attached (watch the progress)
cdt up -d                 # detached  (then: docker compose logs -f conductor)
cdt down                  # stop the stack
cdt ingest                # re-run the ingest only (idempotent)
```

`cdt up` automatically:

- **detects an NVIDIA GPU** + Docker's NVIDIA runtime and enables the GPU for
  Ollama (≈0.5 s per embed); otherwise it prints that it is running on CPU;
- **fetches the books** from the library repo (`CONDUCTOR_LIBRARY_REPO@REF`,
  default [`eltonssouza/conductor-library`](https://github.com/eltonssouza/conductor-library));
- runs the bootstrap and prints the progress of each step:

```
[1/4] fetching library from eltonssouza/conductor-library@main ... 136 .md books
[2/4] pulling bge-m3:  73.4%
      bge-m3 on GPU (0.7 GB VRAM) — fast embeds
[3/4] ChromaDB is up
[4/4] ingesting books ... 60349 chunks indexed
[done] RAG stack ready
```

The bootstrap is **idempotent**: it skips a populated library, skips an
already-pulled model, and upserts the index — so an interrupted run resumes. After
it finishes, the `conductor` service exits; **Ollama and ChromaDB keep running** to
serve queries. ChromaDB is exposed on `localhost:8001`, Ollama on `localhost:11434`
(both bound to localhost only).

### Diary backend (Honcho) — `cdt honcho up`

[Honcho](https://honcho.dev) is the long-term memory behind the diary: it stores
the journal messages and reasons over them in the background, so `cdt journal
recall` answers by *meaning*, not keywords. The diary's local JSONL mirror works
without Honcho, so this backend is **optional** — it adds intelligent recall on top.

```bash
pip install -e .[honcho]                       # the Honcho SDK
cdt honcho setup --provider deepseek     # writes the .env (key auto-read, see below)
cdt honcho up                            # clone + build + start (one command)
cdt honcho down                          # stop
```

`cdt honcho up` does everything the stack needs automatically — it clones
Honcho if missing, fixes the Windows CRLF line endings that break the container
entrypoint, builds from the local clone, brings the stack up (api + deriver +
Postgres/pgvector + Redis), and — on a fresh database — reconfigures the vector
dimension to 1024 for the local `bge-m3` embeddings.

> **Note:** run `cdt up` as well. Honcho embeds its messages using the same
> local `bge-m3` that the RAG stack's Ollama serves.

**Reasoning vs. embeddings.** `cdt honcho setup` ships presets for
`openai | deepseek | openrouter | ollama | anthropic`. Because DeepSeek (and
Anthropic / OpenRouter) have no compatible embeddings API, Conductor uses a
**hybrid** by default:

- **Reasoning** (deriver + dialectic + summary) → your chosen provider (e.g.
  DeepSeek `deepseek-chat`).
- **Embeddings** → the **local Ollama `bge-m3`** (free, 1024-d).

### Where to put the DeepSeek API key

Create the file **`C:\honcho\deep-seek-key.txt`** containing a line in this form:

```
API-KEY-DEEP_SEEK: "sk-your-deepseek-key"
```

When you run `cdt honcho setup --provider deepseek` **without** `--api-key`,
Conductor reads the key from that file and writes it into the (gitignored) Honcho
`.env`. The key is never passed on the command line or printed.

- Override the path with the environment variable `CONDUCTOR_DEEPSEEK_KEY_FILE`.
- You can still pass the key explicitly: `cdt honcho setup --provider
  deepseek --api-key sk-...`.
- Get a key at <https://platform.deepseek.com/>.

To use the **fully local, key-free** option instead:

```bash
docker exec conductor-ollama-1 ollama pull qwen2.5:3b   # a tools-capable chat model
cdt honcho setup --provider ollama --model qwen2.5:3b
cdt honcho up
```

---

## Using Conductor in a project

### `cdt init`

Run it inside the project you want to conduct:

```bash
cd /path/to/your-project
cdt init                       # detect type + stack, scaffold everything
cdt init --all                 # scaffold all 36 roles (default: a relevant subset)
cdt init --roles backend-engineer,security-engineer,quality-assurance
cdt init --type backend --force   # force the type / re-initialize
```

It detects the project type from its manifests (Angular/React/Vue/Next,
Maven/Gradle/Go/Python/.NET/Rust, Flutter/React-Native/Xcode…) and generates,
**inside the project**:

```
<project>/
  CLAUDE.md                     # the project guide: roles + memory + the 11-gate flow + CLI
  .claude/
    agents/<role>.md            # a relevant subset of role Agents (Claude Code loads these)
    skills/<skill>/SKILL.md     # the matching Skills
    commands/cdt.md             # the /cdt flow driver (the interactive gate loop)
    settings.local.json         # machine-local hooks: Honcho capture + context injection
  .cdt/
    config.json                 # enrollment: slug, type, selected roles, Honcho workspace
    stack/<TYPE>.md             # the detected technologies (steers RAG queries)
    memory/                     # the project memory tree:
      diary/                    #   append-only machine diary (JSONL, local)
      daily/                    #   human-readable digests generated from the diary
      docs/                     #   living knowledge (architecture/api/db/ops), ingested into Honcho
      records/                  #   dated artefacts: bugs, ADRs, discovery, features, gaps
      refs/                     #   pointers to external systems (Jira/PRD/SQL/images), never ingested
      _index.md                 #   a live map of what each folder holds
```

`.claude/agents` and `.claude/skills` are **project-scoped Claude Code
directories**, so when you open the project in Claude Code they are loaded
automatically — **no plugin required**. The role subset is chosen by project type
(a frontend project gets FE/UXD/UID/UXR + the core engineering/quality/security
roles; a backend project gets BE/SA/DBA/AppSec/SRE + core; etc.). Use `--all` for
every role or `--roles` to pick exactly.

After initializing, open the project in Claude Code. `CLAUDE.md` becomes the
project's context and instructs Claude to conduct work through the gates while
grounding decisions in the two memories.

### `cdt sync` — the living CLAUDE.md

The generated `CLAUDE.md` is a **living, standardized document**. A managed region
(delimited by `<!-- conductor:managed:start --> … <!-- conductor:managed:end -->`)
is owned by Conductor; anything you write **below the end marker is preserved**.

```bash
cdt sync               # re-detect the stack, refresh the roles, pull diary memory
```

`sync` regenerates only the managed region: it re-detects the stack, re-selects the
role subset (if the project type changed), and pulls the most recent diary
decisions into a "Project memory" block. Recording a journal entry
(`cdt journal add`) also refreshes that block automatically, so the file
stays current as the project evolves.

---

## The 11-gate flow

The generated `CLAUDE.md` instructs Claude to conduct each demand through 11 gates,
**in order**, delegating to the right roles at each step and refusing to advance
until the gate's exit criterion is met.

| # | Gate | Lead roles | Exit criterion |
|---|------|-----------|----------------|
| 1 | Domain discovery & modeling | PM, PO, BA, UX Researcher | problem & hypothesis stated; ubiquitous language; actors & rules identified |
| 2 | Specification (source of truth) | PO, BA, QA | every item has **testable** acceptance criteria with Given/When/Then examples |
| 3 | Security & privacy by design | Security Eng, AppSec, DPO, CISO | threats modeled (STRIDE), mitigations & secure defaults; lawful data handling |
| 4 | Architecture & defensive design | Software/Solutions/Enterprise Architect, Tech/Staff/Principal | ADRs recorded; boundaries & failure modes defined |
| 5 | Test-first / executable spec | SDET, QA, SWE | tests derived from acceptance criteria, **failing before** implementation |
| 6 | Implementation (clean code) | SWE, FE, BE, FSE | green tests; readable, refactored code; edge cases handled |
| 7 | CI + quality gate | DevOps, Platform Eng, SDET | pipeline green (build + tests + static analysis); blocks merge on failure |
| 8 | Validation against the spec | QA, BA, PO | every acceptance criterion verified against the result |
| 9 | Progressive delivery | DevOps, Platform Eng, SRE | rollout strategy (flag/canary/blue-green) with automatic rollback |
| 10 | Observability & operation | SRE, DevOps | SLIs/SLOs instrumented; actionable, symptom-based alerts |
| 11 | Continuous learning | SRE, Eng Manager, Agile Coach | blameless postmortem; each learning fed back as a new spec/test (loop → Gate 2) |

**Run it with `/cdt`.** The flow is driven by the **`/cdt <demand>`** slash
command (installed into `.claude/commands/`). It is the control loop that turns
the flow from passive guidance into enforced steps — and it is **interactive by
design**, stopping for your approval at every gate. Driving a demand any other way
(or pairing `/cdt` with "run autonomously / commit each step") leaves the gates as
passive text that a normal prompt will bypass.

**Mandatory gate protocol.** At every gate the flow requires five steps before
advancing — they are part of the exit criterion, not optional suggestions:

1. **Recall** prior context — `cdt journal recall "<the gate's question>"`.
2. **Ground** claims in the library — `cdt library --gate N "<question>"` and
   **cite the book** for each non-trivial decision. A claim with no citation
   fails the gate.
3. **Delegate** the work to the gate's roles **via the Task tool (as subagents)**,
   not inline — so each Agent runs on its declared `model` tier
   (opus/sonnet/haiku), overriding the session default.
4. **Record** key decisions/errors/solutions — `cdt journal add --gate N
   --kind decision "…"`.
5. **Halt** at a user checkpoint — present the decisions, citations, and open
   risks, then **ask you to approve** before the next gate begins.

This closes the loop: Gate 11's learnings flow back into Gate 2 on the next cycle,
and each loop lowers the defect rate.

---

## The library (Chroma) — grounding answers

The **library** is a RAG over a corpus of reference books. It is *static
knowledge*: "what good engineering practice says." Agents query it to anchor
decisions in real sources instead of relying on the model's memory (this fights
hallucination).

```bash
cdt library "STRIDE threat model"
cdt library -k 8 --json "circuit breaker vs bulkhead"
cdt library --category 09_seguranca_e_privacidade "data minimization"
```

How it works: the question is embedded by **bge-m3** (served by Ollama on the GPU),
then matched against the **ChromaDB** vector index of the corpus; the top-k passages
are returned with their source book and a similarity score. `cdt library`
talks to the dockerized ChromaDB on `localhost:8001` by default (no environment
setup needed once `cdt up` is running).

**When do the agents use it?** On demand, at each gate, whenever a role needs to
ground a decision — the mandatory gate protocol requires a library citation for
every non-trivial claim. Queries are made *project-aware* using the detected stack
in `.cdt/stack/<TYPE>.md` (e.g. a frontend project turns "component architecture"
into "component architecture in Angular"). The agents do not query Chroma
autonomously in the background; Claude runs `cdt library` as instructed by
`CLAUDE.md`.

To (re)build the index, run `cdt up` (or `cdt ingest`); it indexes the
markdown books from `to-brain.7z` — roughly 60k chunks for the default corpus.
Ingest is **incremental**: each chunk stores a content hash, so a re-run skips
everything that is unchanged and only re-embeds new or edited chunks (embedding is
the slow step). Use `cdt ingest --force` to re-embed the whole corpus and
`--quiet` to silence the per-batch telemetry. Embedding (Ollama) and the ChromaDB
upsert run pipelined on separate threads, so the database write of one batch
overlaps the embedding of the next.

**Adding books after the first ingest.** A file dropped straight into the library
directory is not embedded automatically (the dockerized bootstrap skips extraction
once the library is populated). Index it without a full rebuild:

```bash
cdt library reindex                       # scan the library, embed only the new/changed files
cdt library add "<path/to/Book.md>" …     # index specific files already under the library
```

Both reuse the incremental, content-hash-deduped indexer, so they only embed what
is genuinely new. The 3D viewer's [screen ingest](#the-3d-viewer--screen-ingest)
does the same thing from the browser, and additionally writes the formatted file
into the library for you.

---

## The 3D viewer & screen ingest

`cdt viewer` opens a small local web app (standard-library HTTP server, no
web framework) that **visualizes the library embeddings in 3D** and lets you
**ingest a markdown file from the browser**.

```bash
cdt viewer                 # http://localhost:8765, opens the browser
cdt viewer --port 9000 --no-browser
```

It needs the `rag` extra (`pip install -e .[rag]`, which also pulls `scikit-learn`
and `numpy`) and a running ChromaDB (`cdt up`). It is read-only against the
index except through the ingest screen.

**3D map.** The viewer projects the 1024-dimensional `bge-m3` embeddings down to
three dimensions with **PCA** and renders an interactive Plotly scatter colored by
category. To stay fast on the ~60k-chunk index, the projection (and the per-source
centroids used by the graph) is **computed once** on first run and cached to
`~/.claude/conductor/viewer_index.json`; every view, profile filter, and graph is
then served from that cache in milliseconds, and it is rebuilt automatically when
the index changes (a new ingest). Two dropdowns filter by **profile** — the
`category` (the `NN_…` corpus folder) and the `source` (the book) — and hovering a
point shows its source, section, and a text preview.

**3D graph (`/graph`).** A force-directed network rendered with **three.js**
(`3d-force-graph`): each source (book) is a node grouped under its category hub,
and sources are linked to their nearest neighbors by embedding similarity (cosine
between per-source centroids). The kNN web clusters related books and bridges
categories, with the big hub nodes labeled — pick a category (profile) or show them
all. Rotatable/zoomable in 3D.

**Screen ingest.** The "+ Ingest" screen accepts a `.md` file (pick a file or paste
markdown) plus an optional title, author, and category (profile). Conductor
**formats it to the library convention** (see `to-brain/CONVENCOES_DE_ARQUIVOS.md`):
it strips control characters, normalizes blank lines, ensures blank lines around
headings so chunking splits cleanly, and rebuilds a clean header (`# Title` +
optional `**Author**`). The result is saved as `category/Title - Author.md` under
the library, then chunked, embedded, and upserted into ChromaDB — the new source
appears in the 3D map's filters immediately.

---

## The diary (Honcho) — project memory

The **diary** is *dynamic knowledge*: "what this project decided and learned." Every
entry is written to the **local memory tree** first (`.cdt/memory/`, so it works
offline) and then best-effort synced to **Honcho**, which reasons over the history
in the background. Each project gets its own isolated Honcho workspace (keyed by the
project slug).

```bash
# Record (kinds: reasoning | decision | plan | error | solution | checkpoint)
cdt journal add --gate 4 --kind decision "chose hexagonal architecture; ADR-001"
cdt journal add --owner --kind plan "MVP first; auth in phase 2"   # attribute to you

# Recall by meaning, then act on it
cdt journal recall "why did we choose this architecture?"
cdt journal recall --type adr "decisions about persistence"   # scope to a memory facet

# Read solved problems straight out of the diary
cdt journal log --kind error,solution
cdt journal log --kind decision --gate 6

cdt journal digest                 # regenerate the human-readable daily/ digests
cdt journal ingest                 # ingest docs/ + records/ markdown into Honcho (hash-idempotent)
```

With the Honcho backend running, `recall` returns a **reasoned answer** synthesized
from the relevant past entries (the "dialectic"). Without it (or offline), `recall`
falls back to a keyword scan of the local memory — so the diary is always usable.
Recording an entry also refreshes the "Project memory" block in `CLAUDE.md`.

**Live memory (peer modeling + context injection).** Beyond deliberate entries,
`cdt init` installs two Claude Code hooks (in `.claude/settings.local.json`) that
make Honcho a memory that *learns about you*:

- **Capture** (`cdt journal observe`, on `UserPromptSubmit`) appends *your* prompts
  to a local log with zero network overhead, then batches them to Honcho's `owner`
  peer at session boundaries — feeding Honcho's peer modeling.
- **Inject** (`cdt journal context`, on `SessionStart`) asks Honcho what it knows
  about this project and you, and prints it so Claude Code adds it to the session
  context.

Capture is owner-only and the hooks are no-ops outside an enrolled project; the
local capture log is git-ignored. Because Honcho is model-independent, you can swap
the underlying LLM without losing what it has learned.

---

## CLI reference

| Command | What it does |
|---------|--------------|
| `cdt init [path]` | Enroll a project: generate `.claude/` (role subset + the `/cdt` driver + hooks), `.cdt/` (stack, memory tree), and `CLAUDE.md`. Flags: `--all`, `--roles a,b`, `--type T`, `--force`. |
| `cdt sync [path]` | Refresh the managed region of `CLAUDE.md` and the scaffolded driver/hooks/memory tree (re-detect stack, roles, pull diary memory). |
| `cdt library "<q>"` | Semantic search over the reference books. Flags: `-k N`, `--json`, `--category C`, `--gate N`. |
| `cdt library reindex` | Index any library files not yet in ChromaDB (incremental, content-hash skip). |
| `cdt library add <file.md> …` | Index specific `.md` file(s) already under the library directory. |
| `cdt journal add\|recall\|log` | The per-project development diary. `recall --type/--area`, `log --kind error,solution --gate N`. |
| `cdt journal ingest\|digest` | Ingest `docs/`+`records/` into Honcho; regenerate the `daily/` digests. |
| `cdt up` / `down` | Start / stop the Docker RAG stack (GPU auto-detected). |
| `cdt ingest` | (Re)build the library index in the running stack. **Incremental** (content-hash skip). Flags: `--force` (re-embed all), `--quiet` (no telemetry), `--batch N`, `--limit N`. |
| `cdt viewer` | 3D map of the library embeddings (PCA, cached), filtered by profile; includes a screen to ingest a `.md` file formatted to the library convention. Flags: `--port`, `--no-browser`. |
| `cdt honcho setup` | Choose the Honcho reasoning provider and write its `.env`. |
| `cdt honcho up` / `down` | Start / stop the Honcho diary backend (clone + build + health automated). |

`cdt` is the canonical command; `conductor` is kept as a working alias (e.g.
`cdt init` and `conductor init` are equivalent).

---

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONDUCTOR_LIBRARY_REPO` | `eltonssouza/conductor-library` | GitHub repo the corpus is fetched from on `cdt up` |
| `CONDUCTOR_LIBRARY_REF` | `main` | branch/tag of the library repo to fetch |
| `CONDUCTOR_LIBRARY_ARCHIVE` | _(unset)_ | optional offline seed: a mounted `.7z` used instead of the repo fetch |
| `CONDUCTOR_LIBRARY` | `/data/library` (container) · `~/.conductor/library` (host) | corpus markdown root |
| `CONDUCTOR_CHROMA_HTTP` | `localhost:8001` | ChromaDB endpoint used by `cdt library` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (bge-m3) |
| `CONDUCTOR_EMBED_MODEL` | `bge-m3` | embedding model |
| `CONDUCTOR_HNSW_M` / `_CONSTRUCTION_EF` / `_SEARCH_EF` | `32` / `200` / `128` | HNSW index tuning |
| `CONDUCTOR_HONCHO_URL` | `http://localhost:8000` | Honcho API endpoint |
| `CONDUCTOR_DEEPSEEK_KEY_FILE` | `C:\honcho\deep-seek-key.txt` | file holding the DeepSeek key (`API-KEY-DEEP_SEEK`) |
| `CONDUCTOR_HOME` | `~/.claude/conductor` | global registry + staged Honcho clone |
| `HONCHO_SRC` | `~/.claude/conductor/honcho-src` | local Honcho clone used as the build context |

---

## Repository layout

- `conductor/` — the Python package (the CLI):
  - `cli.py` (command dispatch), `detect.py` (project type + stack),
    `roles.py` (the 36-role registry: role → skill / area / project types),
    `scaffold.py` (the `.claude/` + `CLAUDE.md` generator), `project.py`,
    `library.py`, `journal.py`, `honcho_client.py`, `honcho_setup.py`,
    `honcho_stack.py`, `viewer.py` (the 3D map + screen-ingest web app), and
    `rag/` (`core`, `ingest`, `bootstrap`, `stack`).
  - `conductor/templates/` — the 36 role **Agents** + 36 **Skills**,
    `CLAUDE.md.tmpl`, `flow.md` (the 11-gate flow), and `commands/cdt.md` (the
    `/cdt` flow driver). These are copied into target projects.
  - `conductor/infra/conductor/` — the Docker RAG stack (Ollama + bge-m3 + Chroma).
  - `conductor/infra/honcho/` — the self-hosted Honcho diary backend.
- `tools/validate.py` — the invariant validator over the templates (the CI gate).

---

## Invariants / quality gate

`python tools/validate.py` enforces 11 golden rules (R1–R11) over the templates,
the role registry, and the repository. R1–R8 cover the 36 agents + 36 skills
parity, frontmatter and YAML safety, semver, agent anchoring in reference books,
skill structure, the `roles.py` ↔ template registry plus the 11-gate flow, and
valid `model:` tiers. The newer rules add: **R9** — the memory-tree ingestion
routes stay consistent with the scaffolded folders (and `refs/` is never
ingested); **R10** — the `/cdt` driver exists and keeps its enforcement anchors
(RAG citation, subagent delegation, the user checkpoint); **R11** — no real API
keys or tokens are committed to tracked files. It runs in CI
(`.github/workflows/`) and is also Conductor's own Gate 7 for this repository. See
[`tools/README.md`](tools/README.md).

---

## Troubleshooting

- **`cdt library` says "Search failed"** — the RAG stack is not running or
  the index is empty. Run `cdt up` and check `docker compose ps`.
- **First ingest is extremely slow** — it is running on CPU. Install the NVIDIA
  Container Toolkit so `cdt up` can enable the GPU (it auto-detects it).
- **`cdt up` cannot find the Docker files** — the Docker stack is built from
  source, so run it from a clone of this repository (the CLI itself works anywhere).
- **Honcho `recall` returns the local fallback only** — the Honcho backend is not
  up, or the SDK is not installed. Run `pip install -e .[honcho]` and
  `cdt honcho up`. `cdt honcho up` already handles the known Honcho
  self-host issues automatically (Windows CRLF entrypoints, the git-URL build
  context, the 1536→1024 vector-dimension mismatch, and internal-only DB/Redis
  ports).

---

## Security notes

- The DeepSeek key lives in `C:\honcho\deep-seek-key.txt` and is copied into the
  Honcho `.env`, which is **gitignored** — it is never committed or printed. Keep
  that file outside any repository and rotate the key if it leaks.
- The books archive `to-brain.7z` is gitignored (it is data, not source).
- All Docker ports bind to `127.0.0.1` only; nothing is exposed off the host.
