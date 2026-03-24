// @ts-check
import { defineConfig, devices } from '@playwright/test';

/**
 * Configuração do Playwright para testes E2E
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './e2e',
  
  /* Tempo máximo por teste */
  timeout: 30 * 1000,
  
  /* Tempo máximo para expect() */
  expect: {
    timeout: 5000
  },
  
  /* Executar testes em paralelo */
  fullyParallel: true,
  
  /* Falhar o build se houver test.only() */
  forbidOnly: !!process.env.CI,
  
  /* Retry em CI */
  retries: process.env.CI ? 2 : 0,
  
  /* Número de workers */
  workers: process.env.CI ? 1 : undefined,
  
  /* Reporter */
  reporter: [
    ['html', { outputFolder: 'e2e-report' }],
    ['list']
  ],
  
  /* Configuração global */
  use: {
    /* URL base da aplicação */
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'https://workflow-builder-95.preview.emergentagent.com',
    
    /* Recolher trace em caso de falha */
    trace: 'on-first-retry',
    
    /* Screenshot em caso de falha */
    screenshot: 'only-on-failure',
    
    /* Video em caso de falha */
    video: 'on-first-retry',
  },

  /* Configuração de projectos/browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Web server para desenvolvimento local */
  // webServer: {
  //   command: 'yarn dev',
  //   url: 'http://localhost:3000',
  //   reuseExistingServer: !process.env.CI,
  // },
});
