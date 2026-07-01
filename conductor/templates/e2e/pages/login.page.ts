import { Page, Locator } from '@playwright/test';

// Page Object Model — encapsulate selectors so specs read as user intent and a
// selector change touches one file. Prefer data-testid / getByRole over CSS.
export class LoginPage {
  readonly page: Page;
  readonly username: Locator;
  readonly password: Locator;
  readonly submit: Locator;

  constructor(page: Page) {
    this.page = page;
    this.username = page.getByTestId('login-username');
    this.password = page.getByTestId('login-password');
    this.submit = page.getByRole('button', { name: /sign in|entrar/i });
  }

  async goto() {
    await this.page.goto('/login');
  }

  async signIn(user: string, pass: string) {
    await this.username.fill(user);
    await this.password.fill(pass);
    await this.submit.click();
  }
}
