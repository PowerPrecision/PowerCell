/**
 * Testes E2E para fluxo de autenticação
 * Valida login, logout e gestão de sessão
 */
import { test, expect } from '@playwright/test';

// Credenciais de teste
const ADMIN_CREDENTIALS = {
  email: 'admin@sistema.pt',
  password: 'admin'
};

const GESTOR_CREDENTIALS = {
  email: 'powerprecision@sistema.pt',
  password: 'PowerPrecision'
};

test.describe('Autenticação', () => {
  
  test.beforeEach(async ({ page }) => {
    // Ir para página de login antes de cada teste
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
  });

  test('deve mostrar formulário de login', async ({ page }) => {
    // Verificar elementos do formulário usando data-testid
    await expect(page.locator('[data-testid="login-email-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-password-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="login-submit-btn"]')).toBeVisible();
  });

  test('deve mostrar erro com credenciais inválidas', async ({ page }) => {
    // Preencher com credenciais inválidas
    await page.locator('[data-testid="login-email-input"]').fill('invalid@test.com');
    await page.locator('[data-testid="login-password-input"]').fill('wrongpassword');
    
    // Submeter formulário
    await page.locator('[data-testid="login-submit-btn"]').click();
    
    // Aguardar resposta e verificar que não navegou
    await page.waitForTimeout(3000);
    
    // Deve continuar na página de login
    expect(page.url()).toContain('/login');
  });

  test('deve fazer login como admin com sucesso', async ({ page }) => {
    // Preencher credenciais válidas
    await page.locator('[data-testid="login-email-input"]').fill(ADMIN_CREDENTIALS.email);
    await page.locator('[data-testid="login-password-input"]').fill(ADMIN_CREDENTIALS.password);
    
    // Submeter formulário
    await page.locator('[data-testid="login-submit-btn"]').click();
    
    // Aguardar redirecionamento para dashboard
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 15000 });
    
    // Verificar que saiu da página de login
    expect(page.url()).not.toContain('/login');
  });

  test('deve fazer login como gestor de documentos', async ({ page }) => {
    // Preencher credenciais
    await page.locator('[data-testid="login-email-input"]').fill(GESTOR_CREDENTIALS.email);
    await page.locator('[data-testid="login-password-input"]').fill(GESTOR_CREDENTIALS.password);
    
    // Submeter
    await page.locator('[data-testid="login-submit-btn"]').click();
    
    // Aguardar redirecionamento
    await page.waitForURL(/\/(staff|dashboard|processos)/, { timeout: 15000 });
  });

  test('deve redirecionar para login se não autenticado', async ({ page }) => {
    // Tentar aceder a página protegida directamente
    await page.goto('/admin');
    
    // Aguardar possível redirecionamento
    await page.waitForTimeout(2000);
    
    // Deve estar na página de login
    expect(page.url()).toContain('/login');
  });
});

test.describe('Sessão e Persistência', () => {
  
  test('deve manter sessão após refresh', async ({ page }) => {
    // Fazer login
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    await page.locator('[data-testid="login-email-input"]').fill(ADMIN_CREDENTIALS.email);
    await page.locator('[data-testid="login-password-input"]').fill(ADMIN_CREDENTIALS.password);
    await page.locator('[data-testid="login-submit-btn"]').click();
    
    // Aguardar login
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 15000 });
    
    // Fazer refresh
    await page.reload();
    await page.waitForTimeout(2000);
    
    // Verificar que continua logado (não redirecionou para login)
    expect(page.url()).not.toContain('/login');
  });
});
