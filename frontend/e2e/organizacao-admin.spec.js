/**
 * Pacote DW — painel de Administração (Empresas + UCR).
 * Corre na suite completa local; não faz parte do smoke de CI.
 */
import { test, expect } from '@playwright/test';

const ADMIN = {
  email: process.env.TEST_ADMIN_EMAIL || 'admin@sistema.pt',
  password: process.env.TEST_ADMIN_PASSWORD || 'admin',
};

test.describe('Organização — Empresas e Utilizadores', () => {
  test('admin vê a página com tabs Empresas e Utilizadores', async ({ page }) => {
    await page.goto('/login');
    await page.locator('[data-testid="login-email-input"]').fill(ADMIN.email);
    await page.locator('[data-testid="login-password-input"]').fill(ADMIN.password);
    await page.locator('[data-testid="login-submit-btn"]').click();
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 20000 });

    await page.goto('/admin/organizacao');
    await expect(page.locator('[data-testid="organization-admin-page"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="tab-empresas"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-acessos"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-acessos"]')).toContainText('Utilizadores');
    await expect(page.locator('[data-testid="btn-new-company"]')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Administração', exact: true })).toBeVisible();

    await page.locator('[data-testid="tab-acessos"]').click();
    await expect(page.locator('[data-testid="org-admin-users-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="btn-new-user"]')).toBeVisible();
    await expect(page.locator('[data-testid="org-admin-users-search"]')).toBeVisible();

    const firstActions = page.locator('[data-testid^="btn-user-actions-"]').first();
    await expect(firstActions).toBeVisible({ timeout: 15000 });
    await firstActions.click();
    await expect(page.getByRole('menuitem', { name: 'Editar Dados' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Gerir Acessos UCR' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: /Desativar|Ativar/ })).toBeVisible();
  });

  test('cria uma empresa pelo Dialog Nova Empresa', async ({ page }) => {
    await page.goto('/login');
    await page.locator('[data-testid="login-email-input"]').fill(ADMIN.email);
    await page.locator('[data-testid="login-password-input"]').fill(ADMIN.password);
    await page.locator('[data-testid="login-submit-btn"]').click();
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 20000 });

    await page.goto('/admin/organizacao');
    await expect(page.locator('[data-testid="btn-new-company"]')).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="btn-new-company"]').click();
    await expect(page.locator('[data-testid="company-form-dialog"]')).toBeVisible();

    const stamp = Date.now();
    const name = `Empresa E2E ${stamp}`;
    await page.locator('[data-testid="company-name-input"]').fill(name);
    await page.locator('[data-testid="company-email-input"]').fill(`geral-${stamp}@e2e.pt`);
    await page.locator('[data-testid="btn-save-company"]').click();

    await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 10000 });
  });
});
