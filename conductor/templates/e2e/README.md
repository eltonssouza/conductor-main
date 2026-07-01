# E2E / smoke tests (Conductor starter)

Harness-agnostic end-to-end + smoke tests using the **Playwright CLI runner**.
They run identically in Claude Code, Codex, OpenCode, and Pi because the runnable
artifact is `npx playwright test` over the shell — **no harness-exclusive browser
plugin/MCP is required**. (A browser MCP, if your harness has one, may help you
*author* tests, but it is never how they run — that keeps the test gate portable.)

## One-time setup

```sh
npm install -D @playwright/test
npx playwright install --with-deps
```

## Run

```sh
# point at your running app (default http://localhost:4200)
E2E_BASE_URL=http://localhost:4200 npx playwright test     # full suite
npx playwright test --grep @smoke                          # smoke subset (merge gate)
npx playwright show-report                                 # open the last HTML report
```

## Conventions

- **Selectors:** prefer `getByRole` / `data-testid` over CSS/text — survives redesigns.
- **Page Object Model:** encapsulate selectors in `pages/`; specs read as intent.
- **Determinism:** seed data via API/fixtures, wait on conditions (never sleeps).
- **Smoke:** tag the critical, merge-blocking journeys `@smoke`; keep it fast.

## Promote into your project

This starter lives under `.cdt/e2e/` so it never clobbers your setup. To adopt it,
copy `playwright.config.ts`, `tests/`, and `pages/` to your project root (or an
`e2e/` folder) and wire `npx playwright test` into CI (Gate 7).

## How Conductor uses it

Gate 5 (test-first) authors the smoke/e2e for the critical journeys against your
real DOM; Gate 7 (quality gate) runs them headless and blocks merge on the smoke
subset.
