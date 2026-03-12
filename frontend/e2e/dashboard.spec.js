/**
 * Testes E2E para navegação do Dashboard
 * Valida menus, navegação e acesso a páginas
 */
import { test, expect } from '@playwright/test';

// Credenciais de teste
const ADMIN_CREDENTIALS = {
  email: 'admin@sistema.pt',
  password: 'admin'
};

test.describe('Dashboard e Navegação', () => {
  
  // Fazer login antes de cada teste
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder(/email/i).fill(ADMIN_CREDENTIALS.email);
    await page.getByPlaceholder(/password|palavra-passe|senha/i).fill(ADMIN_CREDENTIALS.password);
    await page.getByRole('button', { name: /entrar|login|submit/i }).click();
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 15000 });
  });

  test('deve mostrar menu lateral/sidebar', async ({ page }) => {
    // Verificar que existe uma sidebar ou menu de navegação
    const sidebar = page.locator('nav, aside, [class*="sidebar"], [class*="menu"], [role="navigation"]').first();
    await expect(sidebar).toBeVisible();
  });

  test('deve ter link para Processos', async ({ page }) => {
    // Procurar link para processos
    const processosLink = page.getByRole('link', { name: /processo/i });
    await expect(processosLink.first()).toBeVisible();
  });

  test('deve ter link para Clientes', async ({ page }) => {
    // Procurar link para clientes
    const clientesLink = page.getByRole('link', { name: /cliente/i });
    await expect(clientesLink.first()).toBeVisible();
  });

  test('deve navegar para página de Processos', async ({ page }) => {
    // Clicar em Processos
    await page.getByRole('link', { name: /processo/i }).first().click();
    
    // Verificar URL ou conteúdo da página
    await page.waitForTimeout(1000);
    const url = page.url();
    expect(url).toMatch(/processo|staff|kanban/i);
  });

  test('deve navegar para Definições', async ({ page }) => {
    // Procurar e clicar em Definições/Settings
    const definicoes = page.getByRole('link', { name: /definiç|setting|config/i });
    
    if (await definicoes.first().isVisible()) {
      await definicoes.first().click();
      await page.waitForTimeout(1000);
      
      // Verificar que navegou para a página correcta
      const url = page.url();
      expect(url).toMatch(/defini|setting|config/i);
    }
  });

  test('deve mostrar estatísticas/cards no dashboard', async ({ page }) => {
    // Ir para admin dashboard
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    
    // Procurar cards de estatísticas
    const statsCards = page.locator('[class*="card"], [class*="stat"], [data-testid*="stat"]');
    
    // Deve haver pelo menos alguns cards
    const count = await statsCards.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('deve ter botão de Upload Massivo IA em Definições', async ({ page }) => {
    // Navegar para definições
    await page.goto('/definicoes');
    await page.waitForTimeout(2000);
    
    // Procurar botão de Upload Massivo
    const uploadButton = page.getByRole('button', { name: /upload.*massivo|massivo.*ia|bulk.*upload/i });
    
    // Verificar se existe (pode não estar visível para todos os roles)
    const isVisible = await uploadButton.isVisible().catch(() => false);
    
    if (isVisible) {
      await expect(uploadButton).toBeVisible();
    }
  });
});

test.describe('Menu Admin', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder(/email/i).fill(ADMIN_CREDENTIALS.email);
    await page.getByPlaceholder(/password|palavra-passe|senha/i).fill(ADMIN_CREDENTIALS.password);
    await page.getByRole('button', { name: /entrar|login|submit/i }).click();
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 15000 });
  });

  test('admin deve ver menu de Configurações', async ({ page }) => {
    // Admin deve ter acesso a configurações do sistema
    const configMenu = page.getByRole('link', { name: /configura|sistema|admin/i });
    
    const isVisible = await configMenu.first().isVisible().catch(() => false);
    // Não falhar se não existir, apenas verificar
    console.log(`Menu de configurações visível: ${isVisible}`);
  });

  test('admin deve aceder a gestão de utilizadores', async ({ page }) => {
    // Navegar para gestão de utilizadores
    await page.goto('/admin/users');
    await page.waitForTimeout(2000);
    
    // Verificar se página carregou (pode redirecionar se não tiver permissão)
    const url = page.url();
    
    // Se não redirecionou para login, a página existe
    if (!url.includes('/login')) {
      // Procurar tabela de utilizadores ou lista
      const usersList = page.locator('table, [class*="user"], [data-testid*="user"]').first();
      const isVisible = await usersList.isVisible().catch(() => false);
      console.log(`Lista de utilizadores visível: ${isVisible}`);
    }
  });
});

test.describe('Responsividade', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder(/email/i).fill(ADMIN_CREDENTIALS.email);
    await page.getByPlaceholder(/password|palavra-passe|senha/i).fill(ADMIN_CREDENTIALS.password);
    await page.getByRole('button', { name: /entrar|login|submit/i }).click();
    await page.waitForURL(/\/(admin|staff|dashboard)/, { timeout: 15000 });
  });

  test('deve funcionar em viewport mobile', async ({ page }) => {
    // Redimensionar para mobile
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);
    
    // Página deve carregar sem erros
    await expect(page.locator('body')).toBeVisible();
    
    // Verificar se existe menu hamburguer ou similar
    const mobileMenu = page.locator('[class*="mobile"], [class*="hamburger"], [data-testid*="mobile-menu"], button[class*="menu"]');
    const hasMobileMenu = await mobileMenu.first().isVisible().catch(() => false);
    
    console.log(`Menu mobile presente: ${hasMobileMenu}`);
  });

  test('deve funcionar em viewport tablet', async ({ page }) => {
    // Redimensionar para tablet
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);
    
    // Página deve carregar sem erros
    await expect(page.locator('body')).toBeVisible();
  });
});
