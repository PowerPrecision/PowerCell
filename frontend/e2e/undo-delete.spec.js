/**
 * Teste E2E: o "Desfazer" na eliminação de utilizadores deve CANCELAR a
 * eliminação (o utilizador NÃO é removido do backend). Cobre também o caminho
 * inverso: sem "Desfazer", a eliminação é efetivada.
 *
 * Auto-suficiente: cria os utilizadores de teste via API (setup) e limpa-os
 * no fim (teardown). Requer backend (:8001) + frontend (:3000) a correr.
 */
import { test, expect, request as pwRequest } from '@playwright/test';

const ADMIN = { email: 'admin@sistema.pt', password: 'admin' };
const API = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8001/api';

const stamp = Date.now();
const UNDO_NAME = `ZZ Undo ${stamp}`;
const NOUNDO_NAME = `ZZ NoUndo ${stamp}`;

let apiCtx;
let token;
const createdIds = [];

async function login(page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('email_config_dismissed', 'true');
  });
  await page.goto('/login');
  await page.locator('[data-testid="login-email-input"]').fill(ADMIN.email);
  await page.locator('[data-testid="login-password-input"]').fill(ADMIN.password);
  await page.locator('[data-testid="login-submit-btn"]').click();
  await page.waitForURL(/\/(admin|dashboard)/, { timeout: 20000 });
}

async function createUser(name, email) {
  const res = await apiCtx.post(`${API}/admin/users`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name, email, password: 'TempPass123!', role: 'consultor' },
  });
  if (!res.ok()) throw new Error(`create user failed: ${res.status()} ${await res.text()}`);
  const user = await res.json();
  createdIds.push(user.id);
  return user.id;
}

async function userExists(email) {
  const res = await apiCtx.get(`${API}/admin/users`, { headers: { Authorization: `Bearer ${token}` } });
  const users = await res.json();
  return users.some((u) => u.email === email);
}

test.beforeAll(async () => {
  apiCtx = await pwRequest.newContext();
  const res = await apiCtx.post(`${API}/auth/login-v2`, { data: ADMIN });
  token = (await res.json()).access_token;
  await createUser(UNDO_NAME, `zz-undo-${stamp}@example.pt`);
  await createUser(NOUNDO_NAME, `zz-noundo-${stamp}@example.pt`);
});

test.afterAll(async () => {
  for (const id of createdIds) {
    await apiCtx.delete(`${API}/admin/users/${id}`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
  }
  await apiCtx.dispose();
});

async function goToUsersTab(page) {
  await page.goto('/admin/organizacao?tab=utilizadores');
  await expect(page.locator('[data-testid="org-admin-users-tab"]')).toBeVisible({ timeout: 15000 });
}

async function searchUser(page, name) {
  await page.getByPlaceholder('Pesquisar utilizador...').fill(name);
}

async function deleteUserFromRow(page, name) {
  const row = page.locator('tr', { hasText: name });
  await expect(row).toBeVisible({ timeout: 10000 });
  await row.locator('[data-testid^="btn-user-actions-"]').click();
  await page.getByRole('menuitem', { name: 'Eliminar' }).click();
}

test('Desfazer cancela a eliminação (utilizador permanece no backend)', async ({ page }) => {
  test.setTimeout(45000);
  await login(page);
  await goToUsersTab(page);
  await searchUser(page, UNDO_NAME);

  await deleteUserFromRow(page, UNDO_NAME);
  await expect(page.locator('tr', { hasText: UNDO_NAME })).toHaveCount(0, { timeout: 5000 });

  // Desfazer -> restaura e cancela o commit
  await page.getByRole('button', { name: 'Desfazer' }).click();
  await expect(page.locator('tr', { hasText: UNDO_NAME })).toBeVisible({ timeout: 5000 });

  // Esperar para lá da janela de commit (8s) e recarregar (lê do backend)
  await page.waitForTimeout(9000);
  await goToUsersTab(page);
  await searchUser(page, UNDO_NAME);
  await expect(page.locator('tr', { hasText: UNDO_NAME })).toBeVisible({ timeout: 10000 });

  // Confirmação via API: o utilizador ainda existe.
  expect(await userExists(`zz-undo-${stamp}@example.pt`)).toBe(true);
});

test('sem Desfazer, a eliminação é efetivada no backend', async ({ page }) => {
  test.setTimeout(45000);
  await login(page);
  await goToUsersTab(page);
  await searchUser(page, NOUNDO_NAME);

  await deleteUserFromRow(page, NOUNDO_NAME);
  await expect(page.locator('tr', { hasText: NOUNDO_NAME })).toHaveCount(0, { timeout: 5000 });

  // NÃO clicar Desfazer. Esperar para lá da janela de commit e recarregar.
  await page.waitForTimeout(9000);
  await goToUsersTab(page);
  await searchUser(page, NOUNDO_NAME);
  await expect(page.locator('tr', { hasText: NOUNDO_NAME })).toHaveCount(0, { timeout: 10000 });

  // Confirmação via API: o utilizador foi mesmo eliminado.
  expect(await userExists(`zz-noundo-${stamp}@example.pt`)).toBe(false);
});
