# PowerCell CRM - PRD (Product Requirements Document)

## Problema Original
Aplicação CRM para gestão de processos de crédito imobiliário. O utilizador solicitou implementação de todas as correções e melhorias listadas no ficheiro `ideias CreditoIMO.txt`, incluindo bugs (E#), melhorias (M#) e outras alterações (O#).

## Stack Tecnológica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth (access+refresh), AWS S3, python-magic (MIME), slowapi (rate limiting), sentry-sdk, upstash-redis
- **Frontend**: React, TailwindCSS, Shadcn UI, Sonner, Lucide Icons, @sentry/react
- **DB**: MongoDB (via MONGO_URL)
- **Observabilidade**: Sentry (backend + frontend)
- **Cache**: Upstash Redis (REST API, graceful degradation)

## Estado de Implementação - COMPLETO

### Bugs (E#) - TODOS RESOLVIDOS
| ID | Descrição | Estado |
|----|-----------|--------|
| E1.2 | Bloco "Origem dos Dados" visibilidade | IMPLEMENTADO |
| E1.3 | Cores dos bancos no formulário público | IMPLEMENTADO |
| E1.4 | Situação profissional não guardada | IMPLEMENTADO (verificado E2E) |
| E1.6 | Mapeamento S3 correto | IMPLEMENTADO |
| E1.8 | Botões documentos overflow | IMPLEMENTADO |
| E1.9 | Todos os dados do formulário guardados | IMPLEMENTADO (verificado E2E) |
| E2 | Validação formulário + refinanciamento | IMPLEMENTADO |

### Melhorias (M#) - TODOS IMPLEMENTADOS
| ID | Descrição | Estado |
|----|-----------|--------|
| M1-M9 | Todos os items | IMPLEMENTADO |

### Outras (O#) - IMPLEMENTAÇÃO COMPLETA
| ID | Descrição | Estado |
|----|-----------|--------|
| O1 | Validação MIME type | IMPLEMENTADO (magic bytes) |
| O2 | Sentry | IMPLEMENTADO (backend DSN + frontend DSN + tracing) |
| O3 | Rate limiting | IMPLEMENTADO (uploads 30/min, deletes 20/min, AI 10/min) |
| O4 | JWT lifecycle | IMPLEMENTADO (access 24h + refresh 7d) |
| O6 | Skeletons | IMPLEMENTADO (18+ páginas) |
| O7 | Filtros Kanban | IMPLEMENTADO (data + urgência) |
| O8 | Undo toast | IMPLEMENTADO |
| O9 | Card view mobile | IMPLEMENTADO (3 páginas) |
| O10 | Cursor pagination | IMPLEMENTADO (backwards compatible) |
| O13 | Redis cache | IMPLEMENTADO (graceful degradation, TTL 60-300s) |
| O15 | JWT secret produção | IMPLEMENTADO |
| O16 | DOMPurify | IMPLEMENTADO |
| O17 | Password strength | IMPLEMENTADO |
| O18 | Audit logs | IMPLEMENTADO |
| O20/O21 | Contraste amarelo | IMPLEMENTADO |
| O23 | Contagem IA | IMPLEMENTADO |
| O24 | Audit trail unificado | IMPLEMENTADO ("Filme da Lead") |

### Features Extra
- Notificações automáticas de processos atrasados (>7d urgente, >14d atrasado, >21d crítico)
- Banner de alerta no AdminDashboard
- Redis health check no endpoint /api/health

## Items Pendentes (Necessitam Design/Decisão)
| ID | Descrição | Nota |
|----|-----------|------|
| O5 | Encriptação dados sensíveis | Requer chaves KMS |
| O11 | Websockets fallback | WS já funciona, polling opcional |
| O19 | Testes acessibilidade | Precisa axe-core setup |
| O22 | Workflow Engine No-Code | Feature grande - requer UX design |
