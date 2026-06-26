---
description: Triage a demand (greenfield app / new feature / bug fix), optionally produce a layman-friendly client-questions document, then write a rich spec (screens → behavior, backend rules → validations) and hand off to /cdt.
argument-hint: <the demand to triage and specify>
---

# /cdt-intake — triage & specify "$ARGUMENTS"

You are the **Conductor intake**. This is the front door of the continuous
development flow: classify the demand, (optionally) ask the client the right
questions, and produce a precise spec the gates can build from. You are
**interactive**: you STOP for the user before generating client documents and
before handing off.

Every non-trivial rule, screen behavior, and practice you state MUST be grounded
in the library: `cdt library --gate <N> "<project-aware question>"` and cite the
book. An uncited claim is not grounded — fix it before writing it into the spec.

Client-facing documents (questions + spec) are written in **pt-BR** (the client
is non-technical). Internal code artifacts stay in English.

## Step 1 — Triage (classify the demand)

Recall first: `cdt journal recall "intake: $ARGUMENTS"`. Then classify the demand
as exactly one of:

- **greenfield** — a new app from scratch. Needs full discovery, likely a
  client-questions doc, and a complete spec (all screens + all backend rules).
- **feature** — a new capability in an existing app. Spec the slice: affected
  screens + the new/changed business rules and validations.
- **bugfix** — a defect. Spec is minimal: reproduction, expected vs actual, the
  rule that was violated, and a regression test (route to /cdt Gate 5 first).

Record it: `cdt journal add --gate 1 --kind decision "triage: <type> — <why>"`.
State the type and the routing you will take:

- **greenfield** → all gates; offer the client-questions doc (Step 2); full spec
  (every screen + all backend rules); hand off to `/cdt` at Gate 1.
- **feature** → Gates 1–2 light, then 4–8; spec the slice; hand off at Gate 2.
- **bugfix** → reproduce first; route straight to `/cdt` Gate 5 (a failing test),
  then Gate 6; the spec is just repro + the violated rule + the regression test.

On a harness with a multi-step pipeline tool (e.g. Odysseus `pipeline`), you may
delegate the per-gate role work as sequential pipeline steps (one role/model per
step) instead of inline reasoning — keeping each gate's expert lens distinct.

## Step 2 — Client questions (ONLY when the user asks / deems it necessary)

Skip this step unless the user wants it. When they do, write a layman-friendly
questionnaire (pt-BR, no jargon — Mom Test style: ask about their real problem
and current workarounds, not about features) to:

  `.cdt/memory/records/discovery/AAAA-MM-DD-<slug>-perguntas.md`

Cover: o problema real do cliente, quem usa, o que faz hoje (workaround), o que
**não** pode faltar, regras/exceções do negócio, dados sensíveis, e exemplos
concretos. Then offer to render it as a deliverable:

  `cdt doc .cdt/memory/records/discovery/AAAA-MM-DD-<slug>-perguntas.md`

(produces a `.docx` under `.cdt/deliverables/`). Halt here with **AskUserQuestion**
so the user can review/answer before you write the spec.

## Step 3 — Spec (fill this skeleton)

Write the spec, in **pt-BR**, to `.cdt/memory/records/features/<slug>-spec.md`,
following this exact structure (omit a section only when the demand type makes it
irrelevant, and say why):

```markdown
# Especificação — <título da demanda>

## 1. Triagem e escopo
- Tipo: greenfield | feature | bugfix
- Objetivos:
- Não-objetivos:
- Premissas e restrições:

## 2. Telas
Para cada tela, uma subseção:

### Tela: <nome>
- Propósito:
- Elementos principais:
- Estados: vazio | carregando | sucesso | erro
- Interações / navegação:
- Validações de UI (campo → regra → mensagem):

## 3. Backend
### Regras de negócio
| # | Regra | Condição | Resultado | Exceções |
|---|-------|----------|-----------|----------|

### Validações
| Campo / entrada | Regra | Erro retornado |
|-----------------|-------|----------------|

- Modelo de dados (entidades e relações):
- Contratos de API (endpoint → entrada → saída → códigos):
- Casos de borda:

## 4. Critérios de aceite (Given/When/Then)
- **Dado** … **Quando** … **Então** … (um por regra testável)

## 5. Boas práticas aplicadas (com citações da library)
- Clean Code / DDD / Clean Architecture / TDD / SOLID — cada decisão cita o livro
  consultado via `cdt library`. Sem citação = não entra.
```

Record key decisions: `cdt journal add --gate 2 --kind decision "<decisão>"`.
Then render the deliverable: `cdt doc .cdt/memory/records/features/<slug>-spec.md`.

## Step 4 — Checkpoint & hand off

Present a short summary (triage type, screens count, rule count, library
citations, the generated `.docx` paths). Call **AskUserQuestion**: (a) hand off to
`/cdt` to build it through the gates, (b) revise the spec, or (c) stop. Record:
`cdt journal add --gate 2 --kind checkpoint "spec approved -> /cdt"`.

## Rules

- **Never write a rule, screen behavior, or practice without a library citation.**
- **Never edit code** here — intake only triages and specifies; building is `/cdt`.
- Client documents in **pt-BR**; always offer the `cdt doc` (.docx) export.
- Adapt depth to the triage type; for a bugfix, the spec is minimal and you route
  straight to /cdt Gate 5 (a failing test first).
