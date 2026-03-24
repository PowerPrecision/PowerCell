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

### Funcionalidades Extra Implementadas
- Notificacoes automaticas de processos atrasados
- Redis health check no endpoint /api/health
- Motor de Automacao No-Code (O22)
- WebSocket fallback polling (O11)
- Testes acessibilidade axe-core (O19)
- Encriptacao formulario publico (O5)

### Sessao Anterior
- Bug fix: Erro `.includes()` no PublicClientForm
- Required Labels com * vermelho e texto "(obrigatorio)"
- Campo "Trabalha no Estrangeiro" no formulario
- Opcao "Nenhuma" nos bancos (Step 5)
- Configuracoes de Perfis (`/configuracoes-perfis`)
- Gestao do Formulario (`/gestao-formulario`)
- Client Details mostra todos os campos

### Sessao Atual - Campos Personalizados
- **Criacao de campos personalizados**: Admin pode criar campos com tipos texto, dropdown, checkbox, numero, data, sim/nao
- **Editor de opcoes inline**: Para dropdowns e checkboxes, opcoes sao adicionadas via editor inline
- **Atribuicao a qualquer passo**: Campos podem ser adicionados a qualquer passo (1-5) ou ao passo 6 "Informacoes Adicionais"
- **Renderizacao dinamica**: Campos personalizados sao automaticamente mostrados no formulario publico
- **Eliminacao de campos**: Campos personalizados podem ser eliminados (campos do sistema nao podem)
- **Dados guardados**: Valores dos campos personalizados sao guardados com o registo do cliente
- **API publica**: GET /api/public/form-config retorna campos personalizados sem autenticacao

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
- Redis mostra 'error' no preview (DNS bloqueado)
- axe-core reports na consola do browser em modo dev
- Form config routes: /api/admin/form-config/* (admin), /api/public/form-config (publico)
- Custom fields sao armazenados na colecao `form_config` com type="public_form"
- Custom field_key gerado com prefixo `custom_` + uuid hex
