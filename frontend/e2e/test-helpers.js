/**
 * Helpers partilhados para testes E2E
 * Elimina código duplicado entre ficheiros de teste
 */
import { test as base } from '@playwright/test';

/**
 * Credenciais de teste carregadas de variáveis de ambiente.
 * NOTA: Estas credenciais são APENAS para ambientes de teste/desenvolvimento.
 * Em produção, usar autenticação proper com JWT/OAuth.
 */
export const ADMIN_CREDENTIALS = {
  email: process.env.TEST_ADMIN_EMAIL || 'admin@sistema.pt',
  password: process.env.TEST_ADMIN_PASSWORD || 'admin'  // NOSONAR - credencial de teste
};

export const CONSULTOR_CREDENTIALS = {
  email: process.env.TEST_CONSULTOR_EMAIL || 'consultor@sistema.pt',
  password: process.env.TEST_CONSULTOR_PASSWORD || 'consultor'  // NOSONAR - credencial de teste
};

export const MEDIADOR_CREDENTIALS = {
  email: process.env.TEST_MEDIADOR_EMAIL || 'mediador@sistema.pt',
  password: process.env.TEST_MEDIADOR_PASSWORD || 'mediador'  // NOSONAR - credencial de teste
};

/**
 * Faz login com as credenciais fornecidas
 */
export async function login(page, credentials = ADMIN_CREDENTIALS) {
  await page.goto('/login');
  await page.getByPlaceholder(/email/i).fill(credentials.email);
  await page.getByPlaceholder(/password|palavra-passe|senha/i).fill(credentials.password);
  await page.getByRole('button', { name: /entrar|login|submit/i }).click();
  await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 15000 });
}

/**
 * Faz login como admin
 */
export async function loginAsAdmin(page) {
  await login(page, ADMIN_CREDENTIALS);
}

/**
 * Faz login como consultor
 */
export async function loginAsConsultor(page) {
  await login(page, CONSULTOR_CREDENTIALS);
}

/**
 * Faz login como mediador
 */
export async function loginAsMediador(page) {
  await login(page, MEDIADOR_CREDENTIALS);
}

/**
 * Navega para um processo e clica no primeiro card
 */
export async function openFirstProcess(page) {
  await page.goto('/staff');
  await page.waitForTimeout(2000);
  
  const processCard = page.locator('[class*="card"], [class*="process"]').first();
  
  if (await processCard.isVisible()) {
    await processCard.click();
    await page.waitForTimeout(2000);
    return true;
  }
  return false;
}

/**
 * Verifica se um elemento está visível de forma segura
 */
export async function isElementVisible(page, selector) {
  try {
    const element = page.locator(selector).first();
    return await element.isVisible();
  } catch {
    return false;
  }
}

/**
 * Verifica se texto está visível de forma segura
 */
export async function isTextVisible(page, text) {
  try {
    const element = page.getByText(text).first();
    return await element.isVisible();
  } catch {
    return false;
  }
}

/**
 * Test extendido com fixtures de autenticação
 */
export const test = base.extend({
  // Fixture para página autenticada como admin
  adminPage: async ({ page }, use) => {
    await loginAsAdmin(page);
    await use(page);
  },
  
  // Fixture para página autenticada como consultor
  consultorPage: async ({ page }, use) => {
    await loginAsConsultor(page);
    await use(page);
  },
  
  // Fixture para página autenticada como mediador
  mediadorPage: async ({ page }, use) => {
    await loginAsMediador(page);
    await use(page);
  }
});

export { expect } from '@playwright/test';
