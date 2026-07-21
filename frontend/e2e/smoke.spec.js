/**
 * Smoke E2E — suite mínima para CI.
 * Cobre formulário de login + login admin (credenciais via TEST_ADMIN_*).
 */
import { test, expect } from '@playwright/test';

const ADMIN = {
  email: process.env.TEST_ADMIN_EMAIL || 'admin@sistema.pt',
  password: process.env.TEST_ADMIN_PASSWORD || 'admin',
};

test.describe('Smoke', () => {
  test('mostra formulário de login', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('[data-testid="login-email-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-password-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-submit-btn"]')).toBeVisible();
  });

  test('rejeita credenciais inválidas', async ({ page }) => {
    await page.goto('/login');
    await page.locator('[data-testid="login-email-input"]').fill('invalid@test.com');
    await page.locator('[data-testid="login-password-input"]').fill('wrongpassword');
    await page.locator('[data-testid="login-submit-btn"]').click();
    await page.waitForTimeout(2000);
    expect(page.url()).toContain('/login');
  });

  test('login admin com sucesso', async ({ page }) => {
    await page.goto('/login');
    await page.locator('[data-testid="login-email-input"]').fill(ADMIN.email);
    await page.locator('[data-testid="login-password-input"]').fill(ADMIN.password);
    await page.locator('[data-testid="login-submit-btn"]').click();
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 20000 });
    expect(page.url()).not.toContain('/login');
  });
});
