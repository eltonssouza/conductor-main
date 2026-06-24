# Conductor

Conductor is a **global command-line tool** that turns any software project into a
**harness-conducted** project. You run one command inside a project and Conductor
scaffolds harness-native configuration into it: a relevant subset of
**36 industry role Agents + Skills**, the project's detected **tech stack**, and a
generated **project guide** that describes those roles and an **11-gate development
flow** (discovery → spec → security → architecture → test → code → quality gate →
validation → delivery → observability → learning).

Conductor conducts a project through any of several **AI coding harnesses** —
**Claude Code** is the default, and **OpenCode**, **Codex**, and **Pi** are
supported via `cdt init --target` (see [`cdt init`](#cdt-init)). The same
harness-neutral material is projected into each harness's native layout.

Conductor is **not a Claude Code plugin**. It is the tool that *prepares* a
project. The actual reasoning happens in **your** harness (Claude Code by
default), driven by the project-local config and guide that Conductor writes. Two
long-term memories ground every decision:

| Memory | What it knows | Backed by |
|--------|---------------|-----------|
| **Library (RAG)** | what good engineering practice says — a static corpus of reference books | `cdt library` → bge-m3 + ChromaDB (Docker) |
| **Diary (Honcho)** | what *this* project decided and learned over time | `cdt journal` → Honcho (Docker) + a local memory tree |

The work is driven by the **`/cdt` slash command**, an interactive control loop
that walks a demand through the gates and **stops for your approval at each one**.
The diary is **live memory**: harness hooks installed by Conductor (on Claude Code
and Pi) capture your prompts and inject what Honcho remembers back into each new
session, so the project's memory grows as you work and follows you across sessions.

For **loop engineering**, Conductor also scaffolds an autonomous counterpart —
**`/cdt-triage`**, a scheduled discovery loop — and **MCP connectors** (including
Conductor's own memories as a `cdt mcp` server) so the loop can act on real tools.
See [Loop engineering](#loop-engineering--autonomous-triage--mcp).

---

## Quickstart

From install to your first feature (also printed by `cdt quickstart`):

```bash
# 1. Install (once) — one line; see Installation for details
#    macOS / Linux
curl -fsSL https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.sh | sh
#    Windows (PowerShell):
irm https://raw.githubusercontent.com/eltonssouza/conductor-main/main/install.ps1 | iex

# 2. Start the two memories in Docker (once per machine)
cdt up                                 # RAG: Ollama + ChromaDB + ingest the language-agnostic core
cdt library status                     # verify what got ingested
cdt honcho setup --provider deepseek   # diary reasoning — needs a DeepSeek key (see below); or --provider ollama (key-free)
cdt honcho up                          # the Honcho diary backend

# 3. Enroll a project — and add its stack to the library
cd /path/to/your-project
cdt init                               # scaffold .claude/ + .cdt/ + CLAUDE.md + /cdt + hooks
cdt detect                             # see the project's languages/frameworks
cdt up                                 # re-run FROM the project: ingests its stack books too

# 4. Reload Claude Code in that project  -> so the /cdt command and the hooks load

# 5. Drive your first feature through the gates (inside Claude Code)
/cdt implement <your feature>          # interactive: stops for your approval at each gate
```

> **The library fits your stack.** `cdt up` outside a project ingests the
> language-agnostic **core** only. Run it again **from a project** and it adds
> that project's detected languages/frameworks at the right edition (a Java 25 +
> Spring Boot 4 + Angular 21 project adds Core Java, Spring Boot 3 and the Angular
> 21 guide — not the other editions); the global index accumulates the stacks you
> work on. Pick the technologies interactively with **`cdt library stacks`** (a
> menu of every available language/framework + versions), or control it directly
> with `CONDUCTOR_LIBRARY_STACKS=java@25,angular@21` (and `CONDUCTOR_LIBRARY_TIERS`);
> check the result with `cdt library status`.

Handy along the way:

```bash
cdt library "<question>"               # ground an answer in the reference books
cdt journal recall "<question>"        # recall what this project already decided
cdt journal log --kind error,solution  # list problems already solved
cdt sync                               # after upgrading Conductor: refresh an enrolled project
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
   - [Choosing the diary reasoning provider](#choosing-the-diary-reasoning-provider)
5. [Using Conductor in a project](#using-conductor-in-a-project)
   - [`cdt init`](#cdt-init)
   - [Targeting a harness — `--target`](#targeting-a-harness----target)
   - [`cdt sync` — the living CLAUDE.md](#cdt-sync--the-living-claudemd)
6. [The 11-gate flow](#the-11-gate-flow)
7. [Loop engineering — autonomous triage & MCP](#loop-engineering--autonomous-triage--mcp)
7. [The library (Chroma) — grounding answers](#the-library-chroma--grounding-answers)
8. [The diary (Honcho) — project memory](#the-diary-honcho--project-memory)
9. [CLI reference](#cli-reference)
10. [Configuration (environment variables)](#configuration-environment-variables)
11. [Repository layout](#repository-layout)
12. [Invariants / quality gate](#invariants--quality-gate)
13. [Troubleshooting](#troubleshooting)
14. [Security notes](#security-notes)

---

## How it works

```
                ┌───────────────────────────────────────────────────────┐
                │  cdt  (global CLI, installed with the one-liner / uv) │
                └───────────────────────────────────────────────────────┘
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
- **An API key for your chosen diary provider — or none, if you pick the local
  Ollama option.** Honcho's intelligent recall is powered by an LLM you choose at
  setup time (OpenAI, DeepSeek, OpenRouter, Anthropic, any OpenAI-compatible
  endpoint, or local Ollama). Hosted providers need a key; the local-Ollama option
  works **without any key** (the small local model gives weaker results). See
  [Choosing the diary reasoning provider](#choosing-the-diary-reasoning-provider).
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

`[rag]` adds the ChromaDB client + scikit-learn/numpy (`cdt library`; the latter
two are also used by the separate `conductor-viewer` project);
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
- **auto-selects the corpus for your stack** — run from a project and it detects
  the languages/frameworks and ingests only the matching books plus the
  language-agnostic core (`cdt detect` previews the pick; the choice accumulates
  across projects). Pin it explicitly with `CONDUCTOR_LIBRARY_STACKS` / `_TIERS`;
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
cdt honcho setup                         # pick a reasoning provider, writes the .env (see below)
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
`openai | deepseek | openrouter | ollama | anthropic | custom`. Because most
non-OpenAI providers (DeepSeek, Anthropic, OpenRouter, …) have no compatible
embeddings API, Conductor uses a **hybrid** by default:

- **Reasoning** (deriver + dialectic + summary) → your chosen provider (e.g.
  DeepSeek `deepseek-chat`, OpenAI `gpt-4o-mini`, a local Ollama model).
- **Embeddings** → the **local Ollama `bge-m3`** (free, 1024-d). Only the `openai`
  provider uses OpenAI's hosted `text-embedding-3-small` (1536-d).

### Choosing the diary reasoning provider

The LLM that powers Honcho's background reasoning is **not baked in** — you pick it
at setup. Run it interactively or pass a provider:

```bash
cdt honcho setup                         # interactive chooser (lists every provider)
cdt honcho setup --provider ollama       # local, NO API KEY (the easiest start)
cdt honcho setup --provider deepseek     # hosted; key auto-resolved (see below)
cdt honcho setup --provider openai   --model gpt-4o-mini --api-key sk-...
cdt honcho setup --provider openrouter --model google/gemini-2.5-flash --api-key sk-or-...
cdt honcho setup --provider anthropic  --model claude-haiku-4-5 --api-key sk-ant-...
cdt honcho setup --provider custom --base-url https://my-gateway/v1 --model my-model --api-key sk-...
```

| Provider | Endpoint | Needs a key? |
|----------|----------|--------------|
| `ollama` | **local** `host.docker.internal:11434` | **No** — runs on your machine |
| `openai` | `api.openai.com` | Yes |
| `deepseek` | `api.deepseek.com` | Yes |
| `openrouter` | `openrouter.ai` | Yes |
| `anthropic` | native Anthropic API | Yes |
| `custom` | **your** `--base-url` (vLLM, LM Studio, Groq, Together, a gateway…) | usually |

Any OpenAI-compatible endpoint works via `--provider custom --base-url <url>
--model <id> [--api-key <key>]` — no baked-in preset required.

**Local Ollama — the no-API-key choice.** Point Honcho's reasoning at a model
running on your own machine; nothing leaves your box and there is no key to manage:

```bash
docker exec conductor-ollama-1 ollama pull qwen2.5:3b   # a tools-capable chat model
cdt honcho setup --provider ollama --model qwen2.5:3b   # or llama3.1, etc.
cdt honcho up
```

**Key resolution (any hosted provider).** When a key is needed, `cdt honcho setup`
resolves it in this order and writes it into the (gitignored) Honcho `.env` — the
key is never printed:

1. **`--api-key …`** on the command line, or
2. the **env var** `CONDUCTOR_<PROVIDER>_API_KEY` (e.g. `CONDUCTOR_OPENAI_API_KEY`)
   — or the provider's transport var (`LLM_OPENAI_API_KEY` / `LLM_ANTHROPIC_API_KEY`), or
3. a **per-provider key file** `~/.conductor/<provider>-key.txt` (override the path
   with `CONDUCTOR_<PROVIDER>_API_KEY_FILE`). The file holds one token — a bare line,
   `NAME=token`, or `NAME: "token"`. The legacy DeepSeek file
   `~/.conductor/deepseek-key.txt` (var `API-KEY-DEEP_SEEK`, `CONDUCTOR_DEEPSEEK_KEY_FILE`)
   still works, e.g.:
   ```
   API-KEY-DEEP_SEEK: "sk-your-deepseek-key"
   ```
4. otherwise it **prompts** (interactive) or writes a `set-your-<provider>-key`
   placeholder you fill into the `.env` before `cdt honcho up`.

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
    commands/cdt-triage.md      # the /cdt-triage autonomous discovery loop (loop engineering)
    settings.local.json         # machine-local hooks: Honcho capture + context injection
  .mcp.json                     # MCP: Conductor's memories as a server (cdt mcp)
  .mcp.connectors.example.json  # disabled stubs for GitHub/Slack/... connectors to copy in
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

After initializing, open the project in your harness. The project guide
(`CLAUDE.md`, or `AGENTS.md` for the non-Claude harnesses) becomes the project's
context and instructs the harness to conduct work through the gates while
grounding decisions in the two memories.

> The layout above (`.claude/` + `CLAUDE.md`) is what the **default** Claude Code
> target produces. The other harnesses get the same material in their own native
> layout — see [Targeting a harness](#targeting-a-harness----target) below.

### Targeting a harness — `--target`

The same harness-neutral material (the role Agents/Skills, the `/cdt` flow driver,
and the project guide) is projected per harness by an adapter. Pick one or more
with `--target`:

```bash
cdt init                                   # auto-detect the harness present, else claude
cdt init --target claude                   # the default
cdt init --target opencode
cdt init --target codex,pi                 # comma list — emit several at once
cdt init --target all                      # every supported harness
```

| Target | Layout it produces | Project guide |
|--------|--------------------|---------------|
| `claude` *(default)* | `.claude/` — `agents/` + `skills/` + `commands/cdt.md` + `settings.local.json` (hooks) | `CLAUDE.md` |
| `opencode` | `.opencode/` — `agents/` + `skills/` + `commands/cdt.md` + `plugins/` (live-memory hook); `opencode.json` registers the guide | `AGENTS.md` |
| `codex` | `.agents/skills/` — roles folded into native skills (`$skill`-invokable), incl. `cdt` as `$cdt` | `AGENTS.md` |
| `pi` | `.pi/` — `skills/` + `prompts/cdt.md` + `extensions/` (live-memory hook) | `AGENTS.md` |

Notes:

- **Default is auto-detect.** With no `--target`, Conductor emits for whichever
  harness it already finds in the project (e.g. an existing `.opencode/` or
  `AGENTS.md`); if it detects none, it falls back to **Claude Code**.
- **The guide file differs per harness.** Only the Claude target writes `CLAUDE.md`;
  OpenCode, Codex, and Pi write **`AGENTS.md`** instead.
- **Roles vs. skills.** Claude Code and OpenCode get auto-loaded subagents, so a
  role ships as its own Agent. Codex and Pi have no auto-subagents, so each role's
  persona is **folded into its skill**.
- **Live memory** (the Honcho capture/inject hooks) is installed for the harnesses
  that support it — **Claude Code** and **Pi**.
- **The choice persists.** The selected target keys are written to
  `.cdt/config.json`, so [`cdt sync`](#cdt-sync--the-living-claudemd) re-emits the
  same harness(es). Pass `--target` to `sync` to change the set.

### `cdt sync` — the living CLAUDE.md

The generated `CLAUDE.md` is a **living, standardized document**. A managed region
(delimited by `<!-- conductor:managed:start --> … <!-- conductor:managed:end -->`)
is owned by Conductor; anything you write **below the end marker is preserved**.

```bash
cdt sync               # re-detect the stack, refresh the roles, pull diary memory
```

`sync` regenerates only the managed region: it re-detects the stack, re-selects the
role subset (if the project type changed), and pulls the most recent diary
decisions into a "Project memory" block. It re-emits for the **target harness(es)
configured in `.cdt/config.json`** (pass `--target` to change them). Recording a journal entry
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

## Loop engineering — autonomous triage & MCP

`/cdt` is interactive (it stops at every gate). Its **scheduled counterpart** is
**`/cdt-triage`** — an autonomous discovery loop you run unattended on a cadence
(`/loop`, a cron task, or a harness automation like Codex's Automations tab). It:

1. **recalls** prior state from the diary,
2. **scans** recent CI failures, open issues, and recent commits (Gate 1),
3. **triages** each finding into `worth-doing | needs-human | noise`,
4. hands actionable work to a **maker** subagent **in an isolated git worktree**
   (so parallel work can't collide) and a **separate checker** (Gates 7–8), and
5. records everything to the **journal** instead of pausing for you — the journal
   is the on-disk state, so the next run resumes where this one stopped.

You review the journal, not every step. *Build the loop, stay the engineer:*
verification still belongs to you. The automation is emitted per harness by
`cdt init/sync` (Claude: `.claude/commands/cdt-triage.md`; Codex: `$cdt-triage`
skill; etc.).

**MCP connectors — the loop touches real tools.** `cdt init/sync` also scaffolds
MCP configuration into the project:

- **Conductor's own memories as an MCP server** — `cdt mcp` runs a stdio MCP
  server exposing `library_search`, `journal_recall`, and `journal_add`. It is
  registered **live** in the harness's native MCP config (`.mcp.json` for Claude,
  the `mcp` key in `opencode.json` for OpenCode, `[mcp_servers.*]` in
  `.codex/config.toml` for Codex). The server needs the optional extra:
  `pip install 'conductor[mcp]'`.
- **Third-party connector stubs** (GitHub, Slack, …) ship **disabled** — for
  Claude in a companion `.mcp.connectors.example.json`, elsewhere as a disabled
  entry. Fill the token and enable one to let the loop open PRs / post to a
  channel when CI is green.

Emitting is idempotent and merge-not-clobber: re-running `cdt sync` never
duplicates entries or wipes your existing MCP config.

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
is genuinely new.

> **The 3D viewer moved out.** The interactive 3D map of the library embeddings
> (PCA scatter + force-directed graph) plus a token-economy view now live in the
> separate **[`conductor-viewer`](https://github.com/eltonssouza/conductor-viewer)**
> project. It connects read-only to the same ChromaDB this RAG stack runs
> (`cdt up`). See that project's README to install and run it.

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
| `cdt init [path]` | Enroll a project: generate the harness config (role subset + the `/cdt` driver + `/cdt-triage` automation + hooks + MCP config), `.cdt/` (stack, memory tree), and the project guide. Flags: `--target claude\|opencode\|codex\|pi\|all`, `--all`, `--roles a,b`, `--type T`, `--force`. |
| `cdt sync [path]` | Refresh the managed region of `CLAUDE.md` and the scaffolded driver/hooks/memory tree (re-detect stack, roles, pull diary memory). |
| `cdt library "<q>"` | Semantic search over the reference books. Flags: `-k N`, `--json`, `--category C`, `--gate N`. |
| `cdt library reindex` | Index any library files not yet in ChromaDB (incremental, content-hash skip). |
| `cdt library add <file.md> …` | Index specific `.md` file(s) already under the library directory. |
| `cdt journal add\|recall\|log` | The per-project development diary. `recall --type/--area`, `log --kind error,solution --gate N`. |
| `cdt journal ingest\|digest` | Ingest `docs/`+`records/` into Honcho; regenerate the `daily/` digests. |
| `cdt mcp` | Run Conductor's memories (library + journal) as an MCP stdio server (tools `library_search`, `journal_recall`, `journal_add`). Needs the `[mcp]` extra. |
| `cdt up` / `down` | Start / stop the Docker RAG stack (GPU auto-detected). |
| `cdt ingest` | (Re)build the library index in the running stack. **Incremental** (content-hash skip). Flags: `--force` (re-embed all), `--quiet` (no telemetry), `--batch N`, `--limit N`. |
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
| `CONDUCTOR_LIBRARY_TIERS` | `core` | which `software_dev` tiers to ingest (`core,supporting,foundational,optional`) |
| `CONDUCTOR_LIBRARY_STACKS` | _(none)_ | languages/frameworks to add (e.g. `python,angular`); pin an edition with `stack@major` (e.g. `java@25,angular@21` → nearest book version); or `all` |
| `CONDUCTOR_CHROMA_HTTP` | `localhost:8001` | ChromaDB endpoint used by `cdt library` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (bge-m3) |
| `CONDUCTOR_EMBED_MODEL` | `bge-m3` | embedding model |
| `CONDUCTOR_HNSW_M` / `_CONSTRUCTION_EF` / `_SEARCH_EF` | `32` / `200` / `128` | HNSW index tuning |
| `CONDUCTOR_HONCHO_URL` | `http://localhost:8000` | Honcho API endpoint |
| `CONDUCTOR_<PROVIDER>_API_KEY` | _(unset)_ | the diary provider's key (e.g. `CONDUCTOR_OPENAI_API_KEY`); checked before the key file |
| `CONDUCTOR_<PROVIDER>_API_KEY_FILE` | `~/.conductor/<provider>-key.txt` | file holding the diary provider's key (first token on any line) |
| `CONDUCTOR_DEEPSEEK_KEY_FILE` | `~/.conductor/deepseek-key.txt` | legacy alias for the DeepSeek key file (`API-KEY-DEEP_SEEK`); still honored |
| `CONDUCTOR_HOME` | `~/.claude/conductor` | global registry + staged Honcho clone |
| `HONCHO_SRC` | `~/.claude/conductor/honcho-src` | local Honcho clone used as the build context |

---

## Repository layout

- `conductor/` — the Python package (the CLI):
  - `cli.py` (command dispatch), `detect.py` (project type + stack),
    `roles.py` (the 36-role registry: role → skill / area / project types),
    `scaffold.py` (the `.claude/` + `CLAUDE.md` generator), `project.py`,
    `library.py`, `journal.py`, `honcho_client.py`, `honcho_setup.py`,
    `honcho_stack.py`, `mcp_server.py` (the `cdt mcp` stdio server), and `rag/`
    (`core`, `ingest`, `bootstrap`, `stack`).
  - `conductor/templates/` — the 36 role **Agents** + 36 **Skills**,
    `CLAUDE.md.tmpl`, `flow.md` (the 11-gate flow), `commands/cdt.md` (the `/cdt`
    flow driver), and `automations/triage.md` (the `/cdt-triage` autonomous loop).
    These are copied into target projects.
  - `conductor/infra/conductor/` — the Docker RAG stack (Ollama + bge-m3 + Chroma).
  - `conductor/infra/honcho/` — the self-hosted Honcho diary backend.
- `tools/validate.py` — the invariant validator over the templates (the CI gate).

---

## Invariants / quality gate

`python tools/validate.py` enforces 13 golden rules (R1–R13) over the templates,
the role registry, and the repository. R1–R8 cover the 36 agents + 36 skills
parity, frontmatter and YAML safety, semver, agent anchoring in reference books,
skill structure, the `roles.py` ↔ template registry plus the 11-gate flow, and
valid `model:` tiers. The newer rules add: **R9** — the memory-tree ingestion
routes stay consistent with the scaffolded folders (and `refs/` is never
ingested); **R10** — the `/cdt` driver exists and keeps its enforcement anchors
(RAG citation, subagent delegation, the user checkpoint); **R11** — no real API
keys or tokens are committed to tracked files; **R12** — the `/cdt-triage`
automation template exists with its loop anchors and is wired into the scaffold;
**R13** — the MCP `CONNECTORS` catalog (incl. the `conductor` server) exists and
every target implements `emit_mcp`. It runs in CI
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

- The diary provider's key (when one is used) is resolved from `--api-key`, an env
  var, or a per-provider key file under `~/.conductor/`, and is copied into the
  Honcho `.env`, which is **gitignored** — it is never committed or printed. Keep
  any key file outside a repository and rotate the key if it leaks. The local
  Ollama provider needs no key at all.
- The books archive `to-brain.7z` is gitignored (it is data, not source).
- All Docker ports bind to `127.0.0.1` only; nothing is exposed off the host.
