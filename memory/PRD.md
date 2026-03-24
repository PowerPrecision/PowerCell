# PowerCell CRM - PRD (Product Requirements Document)

## Problema Original
Aplicacao CRM para gestao de processos de credito imobiliario com formulario publico, gestao de clientes, processos, documentos, workflow e automacao.

## Stack Tecnologica
- **Backend**: FastAPI, MongoDB, Pydantic, JWT Auth, AWS S3, slowapi, sentry-sdk, upstash-redis
- **Frontend**: React, TailwindCSS, Shadcn UI, Sonner, Lucide Icons, @sentry/react, @axe-core/react
- **DB**: MongoDB (via MONGO_URL)

## Implementacao Completa

### Bugs (E#), Melhorias (M#), Outras (O#) - TODOS IMPLEMENTADOS

### Funcionalidades Extra
- Notificacoes processos atrasados
- Motor Automacao No-Code (O22)
- WebSocket fallback polling (O11)
- Testes acessibilidade axe-core (O19)
- Sentry (O2), Redis cache (O13)
- Bug fix `.includes()` no formulario
- Required Labels `*` vermelho + "(obrigatorio)"
- Campo "Trabalha no Estrangeiro"
- Opcao "Nenhuma" nos bancos (Step 5)
- Configuracoes de Perfis (`/configuracoes-perfis`)
- Gestao do Formulario (`/gestao-formulario`)
- Campos personalizados dinamicos (texto, dropdown, checkbox, numero, data, sim/nao)
- **Templates de formulario** (3 sistema + personalizados)

### Templates de Formulario (Sessao Atual)
- **3 templates de sistema**: Credito Habitacao, Refinanciamento, Credito Pessoal
- **Guardar como template**: Admin pode guardar config atual como template reutilizavel
- **Ativar template**: Substitui config do formulario ativo com 1 clique
- **Duplicar template**: Cria copia editavel de qualquer template
- **Eliminar template**: Apenas templates personalizados podem ser eliminados
- **Refinanciamento**: Step 3 substituido por campos especificos (valor transferencia, prazo, banco atual, spread)
- **Credito Pessoal**: Sem step imovel, focado em situacao financeira

## Tarefas Pendentes

### P1 - Aprovadas
- Configurar alertas de email no Sentry para erros criticos
- Criar relatorio semanal automatico enviado por email aos gestores

### P2 - Backlog Futuro
- Dashboard de performance por consultor

## Credenciais de Teste
- Admin: admin@sistema.pt / admin
- CEO: pedroborges@powerealestate.pt / power2026

## Rotas Importantes
- Form config admin: /api/admin/form-config/*
- Form config publico: /api/public/form-config
- Templates: /api/admin/form-config/templates/*
- Automacao: /api/admin/automation/*
- Perfis: /configuracoes-perfis
- Gestao formulario: /gestao-formulario
