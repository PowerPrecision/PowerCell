# PowerCell CRM - PRD (Product Requirements Document)

## Problema Original
Aplicacao CRM para gestao de processos de credito imobiliario. O utilizador solicitou implementacao de todas as correcoes e melhorias listadas no ficheiro `ideias CreditoIMO.txt`, incluindo bugs (E#), melhorias (M#) e outras alteracoes (O#).

## Stack Tecnologica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth, AWS S3, slowapi, sentry-sdk, upstash-redis
- **Frontend**: React, TailwindCSS, Shadcn UI, Sonner, Lucide Icons, @sentry/react, @axe-core/react
- **DB**: MongoDB (via MONGO_URL)
- **Observabilidade**: Sentry (backend + frontend)
- **Cache**: Upstash Redis (REST API, graceful degradation)

## Estado de Implementacao - COMPLETO

### Todos os Bugs (E#), Melhorias (M#) e Outras (O#) - IMPLEMENTADOS
Consultar CHANGELOG.md para detalhes.

### Funcionalidades Extra Implementadas
- Notificacoes automaticas de processos atrasados
- Redis health check no endpoint /api/health
- Motor de Automacao No-Code (O22)
- WebSocket fallback polling (O11)
- Testes acessibilidade axe-core (O19)
- Encriptacao formulario publico (O5)

### Novas Funcionalidades (Sessao Atual)
- **Bug fix**: Erro `.includes()` no PublicClientForm corrigido (merge draft com defaults)
- **Required Labels**: Campos obrigatorios com * vermelho e texto "(obrigatorio)"
- **Trabalha no Estrangeiro**: Novo campo no formulario (Step 4) e ProcessDetails
- **Opcao Nenhuma**: Botao "Nenhuma" nos bancos do Step 5
- **Configuracoes de Perfis** (`/configuracoes-perfis`): Gestao de permissoes por utilizador (admin/CEO)
- **Gestao do Formulario** (`/gestao-formulario`): Controlo total sobre campos do formulario publico
- **Client Details**: Dialog mostra TODOS os campos mesmo sem preenchimento

## Tarefas Pendentes

### P1 - Aprovadas
- Configurar alertas de email no Sentry para erros criticos
- Criar relatorio semanal automatico enviado por email aos gestores

### P2 - Backlog Futuro
- Dashboard de performance por consultor (tempo de resposta, taxa de conversao, NPS)

## Credenciais de Teste
- Admin: admin@sistema.pt / admin
- CEO: pedroborges@powerealestate.pt / power2026

## Notas Tecnicas
- Redis mostra 'error' no preview (DNS bloqueado) - funciona em producao
- axe-core reports na consola do browser em modo dev
- Automation routes: /api/admin/automation/*
- Form config routes: /api/admin/form-config/*
- ProfileSettings: /configuracoes-perfis
- FormManagement: /gestao-formulario
