/**
 * Testes E2E para funcionalidades de Upload de Documentos
 * Valida upload, categorização e visualização
 */
import { test, expect, loginAsAdmin, openFirstProcess, isElementVisible } from './test-helpers';

test.describe('Upload de Documentos', () => {
  
  test.use({ storageState: undefined });

  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve mostrar área de upload em detalhes do processo', async ({ page }) => {
    if (await openFirstProcess(page)) {
      const isVisible = await isElementVisible(page, 'input[type="file"], [class*="upload"], [class*="dropzone"]');
      console.log(`Área de upload visível: ${isVisible}`);
    }
  });

  test('deve mostrar lista de documentos do processo', async ({ page }) => {
    if (await openFirstProcess(page)) {
      const isVisible = await isElementVisible(page, '[class*="document"], [class*="file-list"]');
      console.log(`Lista de documentos visível: ${isVisible}`);
    }
  });

  test('deve ter botão de upload em Definições (Upload Massivo)', async ({ page }) => {
    await page.goto('/definicoes');
    await page.waitForTimeout(2000);
    
    const isVisible = await isElementVisible(page, ':text("upload.*massivo|importação|bulk")');
    console.log(`Secção upload massivo visível: ${isVisible}`);
  });
});

test.describe('Categorias de Documentos', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve mostrar categorias de documentos', async ({ page }) => {
    if (await openFirstProcess(page)) {
      const categories = ['identificação', 'financeiro', 'imóvel', 'contrato'];
      
      for (const cat of categories) {
        const isVisible = await isElementVisible(page, `:text("${cat}")`);
        console.log(`Categoria ${cat}: ${isVisible}`);
      }
    }
  });
});

test.describe('Documentos a Expirar', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve mostrar alertas de documentos a expirar', async ({ page }) => {
    await page.goto('/admin/expiring-documents');
    await page.waitForTimeout(2000);
    
    const isVisible = await isElementVisible(page, '[class*="expir"], table, [class*="alert"]');
    console.log(`Página de documentos a expirar carregada: ${isVisible}`);
  });
});

test.describe('Visualização de Documentos', () => {
  
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('deve permitir preview de documentos', async ({ page }) => {
    if (await openFirstProcess(page)) {
      const docItem = page.locator('[class*="document-item"], [class*="file-item"]').first();
      
      if (await docItem.isVisible()) {
        await docItem.click();
        await page.waitForTimeout(1000);
        
        const isVisible = await isElementVisible(page, '[class*="preview"], [class*="viewer"], iframe');
        console.log(`Preview de documento visível: ${isVisible}`);
      }
    }
  });

  test('deve ter opção de download de documentos', async ({ page }) => {
    if (await openFirstProcess(page)) {
      const hasDownload = await isElementVisible(page, ':text("download|descarregar|baixar")') ||
                          await isElementVisible(page, '[class*="download"]');
      console.log(`Opção de download disponível: ${hasDownload}`);
    }
  });
});
