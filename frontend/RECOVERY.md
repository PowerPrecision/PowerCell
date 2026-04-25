# RECOVERY.md — Plano de Recuperação de Emergência

## 🚨 Se o site cair em produção, segue estes passos:

---

## Opção 1: Rollback Rápido no Render (2 minutos)

### Frontend (Vercel)
1. Aceder a [Vercel Dashboard](https://vercel.com/dashboard)
2. Selecionar o projeto `powercell-frontend`
3. Ir a **Deployments**
4. No deployment anterior (último verde ✅), clicar em **⋮** → **Promote to Production**
5. O rollback está completo em ~30 segundos

### Backend (Render)
1. Aceder a [Render Dashboard](https://dashboard.render.com)
2. Selecionar o serviço `powercell-backend`
3. Ir a **Events**
4. No último deploy com sucesso, clicar em **Redeploy this commit**
5. O backend reinicia em ~60 segundos

---

## Opção 2: Rollback via Git (5 minutos)

```bash
# Ver commits recentes
git log --oneline -10

# Resetar para o último commit estável (NÃO usar --hard em main)
git checkout dev
git log --oneline -5
# Identificar o commit SHA do último deploy estável
git revert <commit-que-partou>   # Cria um commit novo a reverter as alterações
git push origin dev

# Render e Vercel vão fazer deploy automático do novo commit
```

### ⚠️ IMPORTANTE: NUNCA usar `git push --force` em `main`
- Sempre usar `git revert` para criar commits de reversão
- Sempre trabalhar na branch `dev` e fazer merge quando estável

---

## Opção 3: Modo Manutenção Rápido

Se precisares de desligar o site temporariamente:

### Render (Backend)
1. Dashboard → Serviço → **Pause** (pára o backend)
2. O frontend Vercel vai mostrar erros de API mas a UI carrega

### Vercel (Frontend)
1. Dashboard → Settings → **Password Protection** (colocar password temporária)

---

## Arquitetura de Resiliência (Implementada)

### Error Boundaries — 3 Camadas

| Camada | Ficheiro | Função |
|--------|----------|--------|
| **Global** | `Sentry.ErrorBoundary` (App.js) | Último recurso — se TUDO crashar, mostra página de erro fullscreen |
| **Chunk** | `LazyChunkErrorBoundary` (App.js) | Erros de carregamento de chunks (stale deploy) — auto-reload |
| **Por Rota** | `RouteBoundary` → `ErrorBoundary` (App.js) | Se UMA página crashar, as outras continuam a funcionar |

### Como funciona:
```
Sentry.ErrorBoundary (fullscreen fallback)
  └─ LazyChunkErrorBoundary (auto-reload on stale chunks)
      └─ RouteBoundary "Kanban" (se Kanban crashar → mostra erro contido)
      └─ RouteBoundary "Processos" (se Processos crashar → mostra erro contido)
      └─ RouteBoundary "Clientes" (se Clientes crashar → mostra erro contido)
      └─ ... (uma boundary por página)
```

### Auto-Retry
Cada ErrorBoundary tem:
- **3 tentativas** de retry automático
- **Delay de 1.5s** entre tentativas
- **Botão "Tentar novamente"** visível ao utilizador
- **Botão "Página inicial"** como fallback

### Sentry Integration
- **Todos os erros** são enviados ao Sentry automaticamente
- Cada erro tem tags: `error_boundary=<nome do módulo>`
- Event ID é mostrado ao utilizador para referência

---

## Monitorização

### Sentry Dashboard
- URL: https://power-precision.sentry.io
- Ver erros em tempo real
- Filtar por tag `error_boundary` para ver erros por módulo

### Render Logs
- Dashboard → Serviço → **Logs**
- Ver erros de backend em tempo real

---

## Checklist Pre-Deploy

Antes de cada deploy para produção:

- [ ] `npm run build` passa sem erros
- [ ] `npm run lint` passa sem erros de circular dependency
- [ ] Testar manualmente: `/` (formulário), `/login`, `/kanban`, `/processos`
- [ ] Verificar Sentry dashboard — sem novos erros críticos
- [ ] Verificar que `minify: 'esbuild'` está ativo (performance)
- [ ] Confirmar que `sourcemap: 'hidden'` está ativo (debug via Sentry)

---

## Contactos de Emergência

| Papel | Ação |
|-------|------|
| Admin | Rollback via Vercel/Render dashboard |
| Dev | `git revert` + push para `dev` |
| IA Z | Análise de erros Sentry + correção |

---

*Última atualização: $(date +%Y-%m-%d)*
