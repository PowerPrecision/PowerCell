# PowerCell CRM - PRD (Product Requirements Document)

## Problema Original
Aplicação CRM para gestão de processos de crédito imobiliário. O utilizador solicitou implementação de todas as correções e melhorias listadas no ficheiro `ideias CreditoIMO.txt`, incluindo bugs (E#), melhorias (M#) e outras alterações (O#).

## Stack Tecnológica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth (access+refresh), AWS S3, python-magic (MIME), slowapi (rate limiting)
- **Frontend**: React, TailwindCSS, Shadcn UI, Sonner (toasts), Lucide Icons
- **DB**: MongoDB (via MONGO_URL)

## Estado de Implementação - COMPLETO

### Bugs (E#) - TODOS RESOLVIDOS
| ID | Descrição | Estado |
|----|-----------|--------|
| E1.2 | Bloco "Origem dos Dados" visibilidade | IMPLEMENTADO |
| E1.3 | Cores dos bancos no formulário público | IMPLEMENTADO |
| E1.4 | Situação profissional não guardada | IMPLEMENTADO (verificado E2E) |
| E1.6 | Mapeamento S3 correto | IMPLEMENTADO (_find_client_folder com fuzzy match) |
| E1.8 | Botões documentos overflow | IMPLEMENTADO (overflow-x-auto) |
| E1.9 | Todos os dados do formulário guardados | IMPLEMENTADO (verificado E2E) |
| E2 | Validação formulário + refinanciamento | IMPLEMENTADO (validateStep) |

### Melhorias (M#) - TODOS IMPLEMENTADOS
| ID | Descrição | Estado |
|----|-----------|--------|
| M1 | Destacar erros no formulário | IMPLEMENTADO |
| M3 | Criar pasta S3 ao registar | IMPLEMENTADO |
| M4 | Apagar fases do workflow | IMPLEMENTADO |
| M5 | Ordenação alfabética por defeito | IMPLEMENTADO |
| M6 | Email ao criar utilizador | IMPLEMENTADO |
| M7 | NIF empresa para indexação | IMPLEMENTADO (enforced on upload) |
| M8 | Log atividade RGPD | IMPLEMENTADO |
| M9 | Botão guardar config IA | IMPLEMENTADO |

### Outras (O#) - IMPLEMENTAÇÃO ABRANGENTE
| ID | Descrição | Estado |
|----|-----------|--------|
| O1 | Validação MIME type | IMPLEMENTADO (magic bytes) |
| O3 | Rate limiting | IMPLEMENTADO (upload 30/min, delete 20/min, AI 10/min, login 3/hr) |
| O4 | JWT lifecycle | IMPLEMENTADO (access 24h + refresh 7d + rotação) |
| O5 | Direito ao esquecimento | PARCIAL (RGPD deletion implementado, encriptação pendente) |
| O6 | Skeletons | IMPLEMENTADO (18+ páginas convertidas) |
| O7 | Filtros Kanban | IMPLEMENTADO (data + urgência + limpar + contagem) |
| O8 | Undo toast | IMPLEMENTADO (UsersManagementPage) |
| O9 | Card view mobile | IMPLEMENTADO (3 páginas: Clients, FilteredProcess, Users) |
| O10 | Cursor pagination | IMPLEMENTADO (GET /api/clients/registered com cursor + backwards compatible) |
| O12 | Rotas duplicadas | VERIFICADO (não duplicado) |
| O14 | Staff role | VERIFICADO (funciona corretamente) |
| O15 | JWT secret produção | IMPLEMENTADO (validação robusta em config.py) |
| O16 | DOMPurify | IMPLEMENTADO |
| O17 | Password strength | IMPLEMENTADO (frontend indicator + backend validation) |
| O18 | Audit logs | IMPLEMENTADO |
| O20/O21 | Contraste amarelo | IMPLEMENTADO |
| O23 | Contagem IA | IMPLEMENTADO |
| O24 | Audit trail unificado | IMPLEMENTADO ("Filme da Lead" com UnifiedAuditTrail) |

### Feature Extra: Notificações Processos Atrasados
- Backend scheduled task + API endpoint + frontend alert banner
- 3 níveis: >7d urgente, >14d atrasado, >21d crítico (notifica diretores)

## Items que Precisam de Serviços Externos (Não Implementáveis sem Chaves)
| ID | Descrição | Bloqueio |
|----|-----------|---------|
| O2 | Sentry | Precisa de Sentry DSN |
| O11 | Websockets fallback | Opcional (WS já funciona) |
| O13 | Redis cache | Redis não disponível no pod |
| O19 | Acessibilidade | Precisa de setup axe-core |
| O22 | Workflow engine No-Code | Feature grande - requer design prévio |
| O5 | Encriptação dados sensíveis | Parcial - precisa de chaves KMS |
