import { defineConfig, devices } from '@playwright/test';

// Harness-agnostic e2e/smoke config scaffolded by Conductor (.cdt/e2e/).
// Runs via `npx playwright test` in ANY harness (Claude Code, Codex, OpenCode,
// Pi) — no harness-exclusive browser plugin/MCP required.
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:4200';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // Optionally let Playwright start the app under test:
  // webServer: { command: 'npm start', url: BASE_URL, reuseExistingServer: !process.env.CI },
});
