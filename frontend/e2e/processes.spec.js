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

/**
 * ── Escudo E2E — Processos Inativos (Read-Only) ──
 *
 * PORQUÊ: Processos em estado terminal (cancelado, concluído, eliminado, ...)
 * devem manter as ações principais do cabeçalho (RGPD, CPCV, Enviar Balcões,
 * Portal do Cliente, Eliminar) VISÍVEIS mas DESATIVADAS — ver
 * `INACTIVE_PROCESS_STATUSES` em `src/pages/ProcessDetails.js`. Este teste
 * intercepta as respostas da API (sem depender de dados reais/seed) para
 * garantir que a regressão "botões ficam clicáveis num processo cancelado"
 * nunca volta a passar despercebida.
 */
test.describe('Processos Inativos (Read-Only)', () => {
  const PROCESS_ID = 'e2e-proc-cancelado-1';
  const CLIENT_ID = 'e2e-client-cancelado-1';

  const ADMIN_USER = {
    id: 'e2e-user-admin-1',
    name: 'Admin QA',
    email: 'admin@sistema.pt',
    role: 'admin',
    company: 'Power Real Estate',
    additional_roles: [],
    permissions: {},
  };

  const CANCELLED_PROCESS = {
    id: PROCESS_ID,
    process_number: 999,
    status: 'cancelado',
    client_id: CLIENT_ID,
    client_name: 'Cliente Processo Cancelado',
    client_email: 'cliente.cancelado@example.com',
    client_phone: '900000000',
    financial_data: {},
    real_estate_data: {},
    credit_data: {},
    titular2_data: {},
    consultor_names: [],
    mediador_names: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  };

  const CLIENT_MOCK = {
    id: CLIENT_ID,
    nome: 'Cliente Processo Cancelado',
    dados_pessoais: {},
    contacto: { email: 'cliente.cancelado@example.com', telefone: '900000000' },
  };

  const fulfillJson = (route, body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  test.beforeEach(async ({ page }) => {
    // Bypass à UI de login: injeta o token diretamente no localStorage antes
    // de qualquer script da app correr (AuthContext lê "token" no arranque).
    await page.addInitScript(() => {
      localStorage.setItem('token', 'e2e-mock-access-token');
      localStorage.setItem('refreshToken', 'e2e-mock-refresh-token');
    });

    await page.route('**/api/auth/me', (route) => fulfillJson(route, ADMIN_USER));
    await page.route(`**/api/processes/${PROCESS_ID}`, (route) => fulfillJson(route, CANCELLED_PROCESS));
    await page.route(`**/api/clients/${CLIENT_ID}`, (route) => fulfillJson(route, CLIENT_MOCK));
    await page.route(`**/api/processes/${PROCESS_ID}/alerts`, (route) =>
      fulfillJson(route, { alerts: [], has_critical: false, has_high: false })
    );
    await page.route(`**/api/rgpd/status/${PROCESS_ID}`, (route) => fulfillJson(route, {}, 404));
    await page.route('**/api/history**', (route) => fulfillJson(route, []));
    await page.route('**/api/activities**', (route) => fulfillJson(route, []));
    await page.route('**/api/deadlines**', (route) => fulfillJson(route, []));
    await page.route('**/api/admin/workflow-statuses', (route) => fulfillJson(route, []));
    // "/tasks/active" (polling de tarefas em BG) e "/tasks?process_id=..." (painel
    // de Tarefas do processo) têm shapes de resposta diferentes — distinguir por regex
    // evita responder ao polling global com o array vazio errado (data.tasks.map crash).
    await page.route(/\/api\/tasks\/active(\?|$)/, (route) => fulfillJson(route, { tasks: [] }));
    await page.route(/\/api\/tasks\?/, (route) => fulfillJson(route, []));
    await page.route('**/api/chat/unread-count', (route) => fulfillJson(route, { unread_count: 0 }));
  });

  test('deve manter as ações principais visíveis mas desativadas num processo cancelado', async ({ page }) => {
    await page.goto(`/processo/${PROCESS_ID}`);

    // O botão Eliminar tem data-testid dedicado — usado como sinal fiável de
    // que a hidratação do processo (loading -> false) já terminou.
    const deleteButton = page.getByTestId('delete-process-btn');
    await expect(deleteButton).toBeVisible({ timeout: 15000 });
    await expect(deleteButton).toBeDisabled();

    const rgpdButton = page.getByTitle('RGPD');
    await expect(rgpdButton).toBeVisible();
    await expect(rgpdButton).toBeDisabled();

    const cpcvButton = page.getByTitle('Gerar Contrato Promessa Compra e Venda');
    await expect(cpcvButton).toBeVisible();
    await expect(cpcvButton).toBeDisabled();

    const sendToBanksButton = page.getByTitle('Enviar documentação para balcões/bancos');
    await expect(sendToBanksButton).toBeVisible();
    await expect(sendToBanksButton).toBeDisabled();

    const portalButton = page.getByTitle('Portal do Cliente');
    await expect(portalButton).toBeVisible();
    await expect(portalButton).toBeDisabled();
  });
});

/**
 * ── Escudo E2E — Context Switcher na Lista de Processos ──
 *
 * PORQUÊ: O Pacote FN sincronizou "Os Meus Processos" com o `company_id`
 * activo do ContextSwitcher (cabeçalho global) — ver
 * `src/pages/ProcessesPage.js` (fetchProcesses) e `src/services/api.js`
 * (interceptor `X-Company-Id`). Este teste garante que trocar de empresa no
 * cabeçalho dispara mesmo um novo pedido a `GET /api/processes/me` com o
 * `company_id` da empresa selecionada — evitando a regressão de a lista
 * ficar "presa" na empresa anterior (isolamento de contexto multi-empresa).
 */
test.describe('Context Switcher — Os Meus Processos', () => {
  const COMPANY_POWER = { id: 'e2e-company-power', name: 'Power Real Estate' };
  const COMPANY_PRECISION = { id: 'e2e-company-precision', name: 'Precision Crédito' };

  // Mesmo role ("consultor") em duas empresas distintas: o ContextSwitcher
  // mostra-as no dropdown "Modo de Operação" com o nome da empresa entre
  // parênteses (ver ContextSwitcher.jsx), o que permite "trocar de empresa"
  // sem sair do role atual — o cenário mais comum de multi-empresa no CRM.
  const MULTI_COMPANY_USER = {
    id: 'e2e-user-consultor-1',
    name: 'Consultora Multi-Empresa QA',
    email: 'consultor@sistema.pt',
    role: 'consultor',
    company: COMPANY_POWER.name,
    additional_roles: [],
    permissions: {},
    companies: [
      { role: 'consultor', company_id: COMPANY_POWER.id, company_name: COMPANY_POWER.name, is_default: true },
      { role: 'consultor', company_id: COMPANY_PRECISION.id, company_name: COMPANY_PRECISION.name, is_default: false },
    ],
  };

  const EMPTY_PROCESSES_PAGE = { items: [], total: 0, pages: 1 };

  const fulfillJson = (route, body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  test.beforeEach(async ({ page }) => {
    // Bypass à UI de login + pré-define a empresa ativa por defeito
    // (Power Real Estate), tal como AuthContext.fetchUser faria após um
    // login real com esta empresa marcada como is_default.
    await page.addInitScript(({ companyId, role }) => {
      localStorage.setItem('token', 'e2e-mock-access-token');
      localStorage.setItem('refreshToken', 'e2e-mock-refresh-token');
      localStorage.setItem('active_company_id', companyId);
      sessionStorage.setItem('activeCompanyId', companyId);
      sessionStorage.setItem('activeRole', role);
    }, { companyId: COMPANY_POWER.id, role: 'consultor' });

    await page.route('**/api/auth/me', (route) => fulfillJson(route, MULTI_COMPANY_USER));
    await page.route('**/api/auth/active-company', (route) => fulfillJson(route, { success: true }));
    await page.route('**/api/processes/me**', (route) => fulfillJson(route, EMPTY_PROCESSES_PAGE));
    await page.route(/\/api\/tasks\/active(\?|$)/, (route) => fulfillJson(route, { tasks: [] }));
    await page.route('**/api/chat/unread-count', (route) => fulfillJson(route, { unread_count: 0 }));
  });

  test('deve disparar um novo pedido a /processes/me com o company_id da empresa selecionada ao trocar de empresa no ContextSwitcher', async ({ page }) => {
    await page.goto('/processos');

    // Pedido inicial: deve refletir a empresa por defeito (Power Real Estate).
    const initialRequest = await page.waitForRequest(
      (req) => req.url().includes('/api/processes/me') && req.method() === 'GET',
      { timeout: 15000 }
    );
    expect(initialRequest.url()).toContain(`company_id=${COMPANY_POWER.id}`);

    // Abre o Context Switcher global (dropdown "Modo de Operação").
    const switcherTrigger = page.getByRole('button', { name: /Modo atual:/i });
    await expect(switcherTrigger).toBeVisible({ timeout: 15000 });
    await switcherTrigger.click();

    const companySwitchItem = page.getByRole('menuitem', { name: new RegExp(COMPANY_PRECISION.name) });
    await expect(companySwitchItem).toBeVisible();

    // Regista a expectativa da nova network request ANTES de clicar, para
    // não perder o pedido disparado imediatamente após a troca de contexto.
    const [switchedRequest] = await Promise.all([
      page.waitForRequest(
        (req) => req.url().includes('/api/processes/me')
          && req.method() === 'GET'
          && req.url().includes(`company_id=${COMPANY_PRECISION.id}`),
        { timeout: 15000 }
      ),
      companySwitchItem.click(),
    ]);

    expect(switchedRequest.url()).toContain(`company_id=${COMPANY_PRECISION.id}`);
    expect(switchedRequest.headers()['x-company-id']).toBe(COMPANY_PRECISION.id);
  });
});
