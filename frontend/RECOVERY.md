# RECOVERY.md — Plano de Recuperação de Emergência

## 🚨 Se o site cair em produção, segue estes passos:

---

## Opção 1: Rollback Rápido no Render (2 minutos)

### Frontend (Render — Static Site)
1. Aceder a [Render Dashboard](https://dashboard.render.com)
2. Selecionar o serviço **powercell-frontend** (Static Site)
3. Ir a **Events**
4. No último deploy com sucesso, clicar em **Redeploy this commit**
5. O rollback está completo em ~30 segundos

### Backend (Render — Web Service)
1. Aceder a [Render Dashboard](https://dashboard.render.com)
2. Selecionar o serviço **powercell-backend** (Web Service)
3. Ir a **Events**
4. No último deploy com sucesso, clicar em **Redeploy this commit**
5. O backend reinicia em ~60 segundos

### Alternativa: Manual Deploy Rollback
1. Render Dashboard → Serviço → **Settings**
2. Scrolling para baixo até **Build & Deploy**
3. Alterar **Branch** temporariamente para um commit anterior
4. Clicar **Save Changes** → Render faz deploy automático

---

## Opção 2: Rollback via Git (5 minutos)

```bash
# Ver commits recentes
git checkout dev
git log --oneline -10

# Identificar o commit SHA do último deploy estável
# Criar um commit de reversão (NÃO usar --hard)
git revert <commit-que-partou>
git push origin dev

# Render vai fazer deploy automático do novo commit
```

### ⚠️ IMPORTANTE: NUNCA usar `git push --force` em `main`
- Sempre usar `git revert` para criar commits de reversão
- Sempre trabalhar na branch `dev` e fazer merge quando estável
- NUNCA commitar diretamente em `main`

---

## Opção 3: Modo Manutenção Rápido

Se precisares de desligar o site temporariamente:

### Render (Backend)
1. Dashboard → Serviço **powercell-backend** → **Pause**
2. O frontend continua a carregar mas mostra erros de API

### Render (Frontend)
1. Dashboard → Serviço **powercell-frontend** → **Pause**
2. O site fica completamente offline com mensagem de manutenção

---

## Arquitetura de Resiliência (Implementada)

### Error Boundaries — 4 Camadas ("Airbags")

| Camada | Ficheiro | Função |
|--------|----------|--------|
| **Global** | `Sentry.ErrorBoundary` (App.js) | Último recurso — se TUDO crashar, mostra página de erro fullscreen |
| **Chunk** | `LazyChunkErrorBoundary` (App.js) | Erros de carregamento de chunks (stale deploy) — auto-reload |
| **Por Rota** | `RouteBoundary` → `ErrorBoundary` (App.js) | Se UMA página crashar durante lazy-loading, as outras continuam |
| **Por Conteúdo** | `ErrorBoundary` (DashboardLayout.js) | Se o CONTEÚDO de uma página crashar, o Menu Lateral e Header sobrevivem |

### Como funciona:
```
Sentry.ErrorBoundary (fullscreen fallback — último recurso)
  └─ LazyChunkErrorBoundary (auto-reload on stale chunks)
      └─ Routes
          ├─ RouteBoundary "Kanban"
          │     └─ KanbanPage → DashboardLayout
          │           ├─ Sidebar ✅ (sobrevive)
          │           ├─ Header ✅ (sobrevive)
          │           └─ ErrorBoundary "Quadro Geral" ← CONTEÚDO isolado
          │                 └─ Kanban content (se crashar → mostra erro contido, sidebar intacta)
          │
          ├─ RouteBoundary "Processos"
          │     └─ ProcessesPage → DashboardLayout
          │           ├─ Sidebar ✅
          │           ├─ Header ✅
          │           └─ ErrorBoundary "Processos" ← CONTEÚDO isolado
          │
          ├─ RouteBoundary "Clientes"
          │     └─ ClientsPage → DashboardLayout
          │           ├─ Sidebar ✅
          │           ├─ Header ✅
          │           └─ ErrorBoundary "Clientes" ← CONTEÚDO isolado
          │
          ├─ ErrorBoundary "RGPD" ← Páginas públicas (sem DashboardLayout)
          ├─ ErrorBoundary "Formulário Público" ← Landing page pública
          └─ ... (uma boundary por rota)
```

### Resultado: Zero White Screens
- Se o conteúdo de uma página crashar → **Menu Lateral e navegação continuam intactos** ✅
- Se uma página inteira crashar → **Outras páginas continuam acessíveis** ✅
- Se tudo crashar → **Fallback fullscreen amigável com botão de retry** ✅
- Se chunks ficarem stale → **Auto-reload silencioso** ✅

### Auto-Retry
Cada ErrorBoundary tem:
- **3 tentativas** de retry automático
- **Delay de 1.5s** entre tentativas
- **Botão "Tentar novamente"** visível ao utilizador
- **Botão "Página inicial"** como fallback

### Sentry Integration
- **Todos os erros** são enviados ao Sentry automaticamente via `Sentry.captureException`
- Cada erro tem tags: `error_boundary=<nome do módulo>`
- Event ID é mostrado ao utilizador para referência
- Component stack incluída para debug avançado

---

## Monitorização

### Sentry Dashboard
- URL: https://power-precision.sentry.io
- Ver erros em tempo real
- Filtrar por tag `error_boundary` para ver erros por módulo
- Ver source maps desminificados (hidden source maps + Sentry plugin)

### Render Logs
- Dashboard → Serviço → **Logs**
- Ver erros de build e runtime em tempo real

---

## Checklist Pre-Deploy

Antes de cada deploy para produção:

- [ ] `npm run build` passa sem erros
- [ ] `npm run lint` passa sem erros de circular dependency (`import/no-cycle`)
- [ ] Testar manualmente: `/` (formulário), `/login`, `/kanban`, `/processos`, `/admin`
- [ ] Verificar Sentry dashboard — sem novos erros críticos
- [ ] Confirmar que `minify: 'esbuild'` está ativo (performance)
- [ ] Confirmar que `sourcemap: 'hidden'` está ativo (debug via Sentry)

---

## Decisões Arquiteturais

### Porquê 4 camadas?
1. **Global** (Sentry.ErrorBoundary) — Cata tudo o que escapa das outras camadas
2. **Chunk** (LazyChunkErrorBoundary) — Problema comum em SPAs com code splitting
3. **Por Rota** (RouteBoundary) — Isola falhas entre páginas diferentes
4. **Por Conteúdo** (DashboardLayout) — **A camada mais importante para UX**: garante que o Menu Lateral e Header NUNCA desaparecem por culpa de um erro no conteúdo

### Porquê ErrorBoundary no DashboardLayout?
O DashboardLayout renderiza o Sidebar + Header + `{children}` (conteúdo). Se o conteúdo crashar, o React desmonta a árvore inteira. Colocando o ErrorBoundary ANTES de `{children}`, garantimos que:
- Sidebar → **Sempre visível** (navegação preservada)
- Header → **Sempre visível** (pesquisa, notificações, tema, logout)
- Conteúdo → **Isolado** (se crashar, mostra fallback amigável dentro da área de conteúdo)

---

## Contactos de Emergência

| Papel | Ação |
|-------|------|
| Admin | Rollback via Render dashboard (30s) |
| Dev | `git revert` + push para `dev` |
| IA Z | Análise de erros Sentry + correção |

---

*Última atualização: 2025-01-14*
