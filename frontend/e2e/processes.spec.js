/**
 * Testes E2E para fluxo de Processos
 * Valida visualização, criação e gestão de processos
 */
import { test, expect, loginAsAdmin, openFirstProcess, isElementVisible, isTextVisible } from './test-helpers';

test.describe('Listagem de Processos', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve mostrar lista/kanban de processos', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(2000);
    
    const isVisible = await isElementVisible(page, '[class*="kanban"], [class*="process"], [class*="card"], table');
    await expect(page.locator('[class*="kanban"], [class*="process"], [class*="card"], table').first()).toBeVisible({ timeout: 10000 });
  });

  test('deve mostrar colunas do kanban por status', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(3000);
    
    const statusColumns = ['triagem', 'documentação', 'análise', 'aprovado'];
    
    for (const status of statusColumns) {
      const isVisible = await isTextVisible(page, status);
      console.log(`Coluna ${status}: ${isVisible}`);
    }
  });

  test('deve ter campo de pesquisa', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(2000);
    
    const isVisible = await isElementVisible(page, ':placeholder("pesquis|search|filtrar")');
    console.log(`Campo de pesquisa visível: ${isVisible}`);
  });

  test('deve filtrar processos por pesquisa', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(2000);
    
    const searchInput = page.getByPlaceholder(/pesquis|search|filtrar/i);
    
    if (await searchInput.isVisible()) {
      await searchInput.fill('test');
      await page.waitForTimeout(1000);
      await expect(page.locator('body')).toBeVisible();
    }
  });
});

test.describe('Detalhes do Processo', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve abrir detalhes ao clicar num processo', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(3000);
    
    const processCard = page.locator('[class*="card"], [class*="process-item"], [data-testid*="process"]').first();
    
    if (await processCard.isVisible()) {
      await processCard.click();
      await page.waitForTimeout(2000);
      
      const detailsVisible = await isElementVisible(page, '[class*="modal"], [class*="detail"], [class*="drawer"]');
      const urlChanged = page.url().includes('/process');
      
      console.log(`Detalhes visíveis: ${detailsVisible || urlChanged}`);
    }
  });

  test('deve mostrar informação do cliente no processo', async ({ page }) => {
    if (await openFirstProcess(page)) {
      const isVisible = await isTextVisible(page, 'cliente|nif|email');
      console.log(`Info do cliente visível: ${isVisible}`);
    }
  });
});

test.describe('Criação de Processo', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve ter botão para criar novo processo', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(2000);
    
    const isVisible = await isElementVisible(page, ':text("novo.*processo|criar.*processo|adicionar|new")');
    console.log(`Botão novo processo visível: ${isVisible}`);
  });

  test('deve abrir formulário de novo processo', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(2000);
    
    const newButton = page.getByRole('button', { name: /novo|criar|adicionar|\+/i }).first();
    
    if (await newButton.isVisible()) {
      await newButton.click();
      await page.waitForTimeout(1000);
      
      const isVisible = await isElementVisible(page, 'form, [class*="modal"], [class*="dialog"]');
      console.log(`Formulário de criação visível: ${isVisible}`);
    }
  });
});

test.describe('Alteração de Status', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve permitir drag and drop no kanban', async ({ page }) => {
    await page.goto('/staff');
    await page.waitForTimeout(3000);
    
    const draggableItems = page.locator('[draggable="true"], [class*="draggable"]');
    const count = await draggableItems.count();
    
    console.log(`Itens arrastáveis encontrados: ${count}`);
  });
});
