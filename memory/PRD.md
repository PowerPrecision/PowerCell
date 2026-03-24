# PowerCell CRM - PRD (Product Requirements Document)

## Problema Original
Aplicação CRM para gestão de processos de crédito imobiliário. O utilizador solicitou implementação de todas as correções e melhorias listadas no ficheiro `ideias CreditoIMO.txt`, incluindo bugs (E#), melhorias (M#) e outras alterações (O#).

## Stack Tecnológica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth, AWS S3
- **Frontend**: React, TailwindCSS, Shadcn UI, Sonner (toasts), Lucide Icons
- **DB**: MongoDB (via MONGO_URL)

## Estado de Implementação dos Itens do `ideias CreditoIMO.txt`

### Bugs (E#)
| ID | Descrição | Estado |
|----|-----------|--------|
| E1.2 | Bloco "Origem dos Dados" visibilidade | IMPLEMENTADO (visível para todos os staff) |
| E1.3 | Cores dos bancos no formulário público | IMPLEMENTADO (badges coloridos) |
| E1.4 | Situação profissional não guardada | IMPLEMENTADO (confirmado via teste) |
| E1.6 | Mapeamento S3 correto | PENDENTE (P2) |
| E1.8 | Botões documentos overflow | IMPLEMENTADO (overflow-x-auto) |
| E1.9 | Todos os dados do formulário guardados | IMPLEMENTADO (confirmado via teste E2E) |
| E2 | Validação do formulário + refinanciamento | IMPLEMENTADO (validateStep já existe) |

### Melhorias (M#)
| ID | Descrição | Estado |
|----|-----------|--------|
| M1 | Destacar erros no formulário | IMPLEMENTADO (FieldError, ValidatedInput) |
| M3 | Criar pasta S3 ao registar | IMPLEMENTADO |
| M4 | Apagar fases do workflow | IMPLEMENTADO (WorkflowEditor) |
| M5 | Ordenação alfabética por defeito | IMPLEMENTADO |
| M6 | Email ao criar utilizador | IMPLEMENTADO (welcome email) |
| M7 | NIF empresa para indexação | PENDENTE (P2) |
| M8 | Log atividade RGPD | IMPLEMENTADO |
| M9 | Botão guardar config IA | IMPLEMENTADO (código correto, requer teste com credenciais admin) |

### Outras (O#)
| ID | Descrição | Estado |
|----|-----------|--------|
| O1 | Validação MIME type | PENDENTE (P2) |
| O2 | Sentry | PENDENTE (P2) |
| O3 | Rate limiting | PENDENTE (P2) |
| O4 | JWT lifecycle | PENDENTE (P2) |
| O5 | Direito ao esquecimento | PENDENTE (P2) |
| O6 | Skeletons | IMPLEMENTADO (8+ páginas: Admin, Process, FilteredList, ClientReg, AIConfig, UnifiedLogs, Users, MyClients, Kanban) |
| O7 | Filtros Kanban | IMPLEMENTADO (data, urgência, limpar filtros, contagem) |
| O8 | Undo toast | IMPLEMENTADO (UsersManagementPage) |
| O9 | Card view mobile | IMPLEMENTADO (ClientsPage, FilteredProcessList, UsersManagement) |
| O10 | Cursor pagination | PENDENTE (P2) |
| O11 | Websockets fallback | PENDENTE (P2) |
| O12 | Rotas duplicadas admin.py | VERIFICADO (não duplicado) |
| O13 | Redis cache | PENDENTE (P2) |
| O14.1/O14.2 | Staff role | VERIFICADO (funciona corretamente com STAFF_ROLES) |
| O15 | JWT secret produção | PENDENTE (P2) |
| O16 | DOMPurify | IMPLEMENTADO (sanitize.js) |
| O17 | Validação força password | IMPLEMENTADO (frontend indicator + backend validation) |
| O18 | Audit logs | IMPLEMENTADO |
| O19 | Acessibilidade | PENDENTE (P2) |
| O20.1/O20.2 | Contraste amarelo Kanban | IMPLEMENTADO |
| O21 | Contraste amarelo badges | IMPLEMENTADO |
| O22 | Workflow engine | PENDENTE (P2) |
| O23 | Contagem execuções IA | IMPLEMENTADO |
| O24 | Audit trail unificado | PENDENTE (P2) |

## Backlog P2 (Futuro)
1. O1 - Validação MIME type real no servidor
2. O2 - Integração Sentry
3. O3 - Rate limiting rotas críticas
4. O4 - JWT token lifecycle (access curto, refresh revogável)
5. O5 - Direito ao esquecimento + encriptação
6. O10 - Cursor pagination
7. O11 - Websockets fallback
8. O13 - Redis cache para estatísticas
9. O15 - JWT secret único em produção
10. O19 - Testes automatizados de acessibilidade
11. O22 - Motor de automação de workflows No-Code
12. O24 - Audit trail visual unificado
13. E1.6 - Mapeamento S3 (procurar pasta pelo nome)
14. M7 - NIF empresa obrigatório para indexação
15. Skeletons nas restantes ~18 páginas secundárias
