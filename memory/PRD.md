# PowerCell CRM - PRD (Product Requirements Document)

## Problema Original
Aplicacao CRM para gestao de processos de credito imobiliario. O utilizador solicitou implementacao de todas as correcoes e melhorias listadas no ficheiro `ideias CreditoIMO.txt`, incluindo bugs (E#), melhorias (M#) e outras alteracoes (O#).

## Stack Tecnologica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth (access+refresh), AWS S3, python-magic (MIME), slowapi (rate limiting), sentry-sdk, upstash-redis
- **Frontend**: React, TailwindCSS, Shadcn UI, Sonner, Lucide Icons, @sentry/react, @axe-core/react
- **DB**: MongoDB (via MONGO_URL)
- **Observabilidade**: Sentry (backend + frontend)
- **Cache**: Upstash Redis (REST API, graceful degradation)

## Estado de Implementacao - COMPLETO

### Bugs (E#) - TODOS RESOLVIDOS
| ID | Descricao | Estado |
|----|-----------|--------|
| E1.2 | Bloco "Origem dos Dados" visibilidade | IMPLEMENTADO |
| E1.3 | Cores dos bancos no formulario publico | IMPLEMENTADO |
| E1.4 | Situacao profissional nao guardada | IMPLEMENTADO (verificado E2E) |
| E1.6 | Mapeamento S3 correto | IMPLEMENTADO |
| E1.8 | Botoes documentos overflow | IMPLEMENTADO |
| E1.9 | Todos os dados do formulario guardados | IMPLEMENTADO (verificado E2E) |
| E2 | Validacao formulario + refinanciamento | IMPLEMENTADO |

### Melhorias (M#) - TODOS IMPLEMENTADOS
| ID | Descricao | Estado |
|----|-----------|--------|
| M1-M9 | Todos os items | IMPLEMENTADO |

### Outras (O#) - IMPLEMENTACAO COMPLETA
| ID | Descricao | Estado |
|----|-----------|--------|
| O1 | Validacao MIME type | IMPLEMENTADO (magic bytes) |
| O2 | Sentry | IMPLEMENTADO (backend DSN + frontend DSN + tracing) |
| O3 | Rate limiting | IMPLEMENTADO (uploads 30/min, deletes 20/min, AI 10/min) |
| O4 | JWT lifecycle | IMPLEMENTADO (access 24h + refresh 7d) |
| O5 | Encriptacao dados sensiveis | IMPLEMENTADO (Fernet AES-128-CBC + HMAC, PBKDF2) |
| O6 | Skeletons | IMPLEMENTADO (18+ paginas) |
| O7 | Filtros Kanban | IMPLEMENTADO (data + urgencia) |
| O8 | Undo toast | IMPLEMENTADO |
| O9 | Card view mobile | IMPLEMENTADO (3 paginas) |
| O10 | Cursor pagination | IMPLEMENTADO (backwards compatible) |
| O11 | WebSocket fallback polling | IMPLEMENTADO (MAX_WS_FAILS=3, 30s polling) |
| O13 | Redis cache | IMPLEMENTADO (graceful degradation, TTL 60-300s) |
| O15 | JWT secret producao | IMPLEMENTADO |
| O16 | DOMPurify | IMPLEMENTADO |
| O17 | Password strength | IMPLEMENTADO |
| O18 | Audit logs | IMPLEMENTADO |
| O19 | Testes acessibilidade axe-core | IMPLEMENTADO (dev only, dynamic import) |
| O20/O21 | Contraste amarelo | IMPLEMENTADO |
| O22 | Workflow Engine No-Code | IMPLEMENTADO (CRUD API + UI + engine) |
| O23 | Contagem IA | IMPLEMENTADO |
| O24 | Audit trail unificado | IMPLEMENTADO ("Filme da Lead") |

### Features Extra
- Notificacoes automaticas de processos atrasados (>7d urgente, >14d atrasado, >21d critico)
- Banner de alerta no AdminDashboard
- Redis health check no endpoint /api/health

## Tarefas Pendentes

### P1 - Aprovadas
- Configurar alertas de email no Sentry para erros criticos
- Criar relatorio semanal automatico enviado por email aos gestores

### P2 - Backlog Futuro
- Dashboard de performance por consultor (tempo de resposta, taxa de conversao, NPS)

## Credenciais de Teste
- Admin: admin@sistema.pt / admin
- CEO: pedroborges@powerealestate.pt / power2026
- Consultor: tiagoborges@powerealestate.pt / power2026

## Notas Tecnicas
- Redis mostra 'error' no preview (DNS bloqueado) - esperado, funciona em producao
- axe-core reports aparecem na consola do browser em modo dev
- Automation routes: /api/admin/automation/* (requer role admin/ceo)
