# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [Não publicado]

## [2026-03-24] - Pré-visualização para Consultores e Correções de Build

### Adicionado
- **Pré-visualização do Formulário para Consultores**: Botão "Pré-visualizar Formulário" na página de Registos de Clientes. Abre o formulário completo (6 passos) em modo navegável sem obrigar a preencher campos. Rota: `/formulario-consultor`
- Banner "Modo de Pré-visualização" com botão de voltar
- **Ver processos sem atualização**: Botão "Ver processos" no Dashboard expande lista detalhada com Cliente, Estado, Consultor, Dias sem atualização e Urgência. Cada linha é clicável e redireciona para o processo
- **Link S3 automático**: Ao criar processo (atribuir cliente), é gerado automaticamente o campo `s3_folder` no formato `s3://powerprecision-docs-storage/Documentação Clientes/Nome_Do_Cliente/`

### Alterado
- **Tabela de Registos de Clientes**: Filtro por defeito alterado para mostrar apenas clientes **sem processo**. Quando o processo é criado, o cliente desaparece da vista principal
- **Header do formulário**: Link "Acesso Colaborador" escondido no modo de pré-visualização

### Corrigido
- **Build de produção**: Separada a instalação de dependências no Dockerfile em 2 passos (PyPI público + índice privado para `emergentintegrations`). Removidos pacotes conflituosos do `requirements.txt` (`scraperapi-sdk`, `litellm`)
- **Processos sem atualização**: Lista de estados finais corrigida para incluir todas as variações (`concluidos`, `desistencias`, `desistência`, `arquivado`, `perdido`, `eliminado`). Processos concluídos e desistências já não aparecem no alerta

## [2026-03-24] - Templates e Pré-visualização

### Adicionado
- **Templates de Formulário**: 3 templates de sistema pré-definidos (Crédito Habitação, Refinanciamento, Crédito Pessoal)
- **Guardar como Template**: Admin pode guardar a configuração atual como template reutilizável
- **Ativar Template**: Substituir configuração do formulário com 1 clique
- **Duplicar Template**: Criar cópia editável de qualquer template
- **Pré-visualização de Templates**: Ver como o formulário ficará antes de ativar, com renderização mock dos campos
- API endpoints: GET/POST/DELETE `/api/admin/form-config/templates/*`, GET `/api/admin/form-config/templates/{id}/preview`

## [2026-03-24] - Campos Personalizados

### Adicionado
- **Campos Personalizados Dinâmicos**: Admin pode criar campos de 6 tipos (texto, dropdown, checkbox, número, data, sim/não)
- **Editor de Opções Inline**: Para dropdowns e checkboxes, adicionar/remover opções em tempo real
- **Atribuição a qualquer passo**: Campos podem ser adicionados a passos 1-5 ou ao passo 6 "Informações Adicionais"
- **Renderização Automática**: Campos aparecem no formulário público sem alterações de código
- **Eliminação de Campos**: Campos personalizados podem ser eliminados (campos do sistema protegidos)
- Endpoint público: GET `/api/public/form-config` para obter campos personalizados
- API endpoints: POST/DELETE `/api/admin/form-config/custom-field`

## [2026-03-24] - Gestão de Perfis e Formulário

### Adicionado
- **Página Configurações de Perfis** (`/configuracoes-perfis`): Gestão de permissões por utilizador (páginas visíveis + ações permitidas)
- **Página Gestão do Formulário** (`/gestao-formulario`): Ativar/desativar campos, marcar como obrigatórios
- Links na sidebar do admin/CEO para as novas páginas
- Campo `permissions` no modelo de utilizador (pages + actions)

## [2026-03-24] - Melhorias no Formulário Público

### Adicionado
- Campo "Trabalha no estrangeiro?" no Step 4 do formulário e nos detalhes do processo
- Opção "Nenhuma" nos bancos do Step 5 (créditos ativos e simulações)
- Labels obrigatórios com `*` vermelho e texto "(obrigatório)"
- Dialog de detalhes do cliente mostra TODOS os campos (incluindo vazios com "Não preenchido")

### Corrigido
- **Bug crítico**: `Cannot read properties of undefined (reading 'includes')` no PublicClientForm
  - Causa: Drafts antigos no localStorage não tinham os arrays `caracteristicas`, `bancos_creditos`, `bancos_simulacoes`
  - Fix: Merge de draft com defaults + safety guards `(array || []).includes()`
- Corrigido padrão unsafe em `DashboardShared.js` para `client_name`/`client_email` potencialmente undefined

## [2026-03-24] - Backlog P2 Completo

### Adicionado
- **O22 - Motor de Automação No-Code**: CRUD de regras "Se X, Então Y" com triggers (process_created, status_changed, etc.) e ações (send_notification, change_status, assign_user)
- **O11 - WebSocket Fallback**: Polling HTTP automático quando WebSocket falha (MAX_WS_FAILS=3, 30s interval)
- **O19 - Testes Acessibilidade**: axe-core integrado no ambiente de desenvolvimento (consola do browser)
- **O5 - Encriptação**: Fernet AES-128-CBC aplicada ao formulário de registo público

## [2026-03-23] - Integrações e Cache

### Adicionado
- **O2 - Sentry**: SDK configurado no frontend e backend para monitorização de erros em tempo real
- **O13 - Redis Cache**: Cache com Upstash Redis nos endpoints de estatísticas (TTL 60-300s, degradação graciosa)
- **Notificações de Processos Parados**: Tarefa agendada para detetar processos sem atividade (>7d urgente, >14d atrasado, >21d crítico)
- **O24 - Audit Trail Unificado**: Componente "Filme da Lead" integrado nos detalhes do processo

## [2026-03-23] - Correções em Lote (P0/P1)

### Adicionado
- **O6 - Skeletons**: Loading skeletons em 18+ páginas
- **O7 - Filtros Kanban**: Filtros por data e urgência no quadro Kanban
- **O8 - Undo Toast**: Ação de desfazer com toast em operações destrutivas
- **O9 - Card View Mobile**: Vista de cards para 3 páginas em dispositivos móveis
- **O10 - Cursor Pagination**: Paginação baseada em cursor no endpoint de clientes
- **O3 - Rate Limiting**: Aplicado a uploads (30/min), deletes (20/min), IA (10/min)
- **O4 - JWT Lifecycle**: Access token 24h + refresh token 7d

### Corrigido
- E1.2 - Bloco "Origem dos Dados" visibilidade
- E1.3 - Cores dos bancos no formulário público
- E1.6 - Mapeamento S3 correto
- E1.8 - Botões documentos overflow
- E1.9 - Todos os dados do formulário guardados
- E2 - Validação formulário + refinanciamento
- M1-M9 - Todas as melhorias solicitadas

## [2026-03-20] - Correções de Bugs

### Corrigido
- **RGPD Status Endpoint**: Validação de UUID, tratamento de erros melhorado
- **Temp Links Create Endpoint**: Validação de `process_id` vazio, logging melhorado
- **RGPD Service**: Validação de entrada, parsing de datas corrigido

### Documentação
- Criado README.md e CHANGELOG.md
