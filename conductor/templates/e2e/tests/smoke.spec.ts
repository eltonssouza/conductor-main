import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/login.page';

// Smoke = the small, merge-blocking subset of the critical user journeys.
// Prefer getByRole / data-testid over CSS or text so the suite survives redesigns.
test.describe('@smoke', () => {
  test('app loads', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/.+/);
  });

  // Example journey (login -> dashboard). Fill in real selectors/data for your app,
  // then remove `.skip`. Credentials come from env, never hard-coded.
  test.skip('login reaches the dashboard', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(process.env.E2E_USER!, process.env.E2E_PASS!);
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible();
  });
});
