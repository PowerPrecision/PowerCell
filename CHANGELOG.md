# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [Não publicado]

## [2026-04-02] - Correções de Bugs

### Corrigido
- **Erro 500 em PATCH /system-config/dsti_analysis**: A secção `dsti_analysis` estava definida em CONFIG_FIELDS mas não tinha handler na função `update_config_section()`. Adicionado handler e import de `DSTIConfig` para actualizar correctamente as configurações de análise DSTI (enabled, high_risk_threshold, critical_risk_threshold).
- **AWS Secret Key - Olho de revelação não funcionava**: O endpoint `/reveal-secrets` tinha a sua própria lista de `sensitive_fields` que não incluía `aws_secret_access_key`. Ao clicar no olho, a API não retornava o valor real. Adicionado `aws_secret_access_key` à lista de campos reveláveis.
- **Auto-fill CC - 5 bugs corrigidos end-to-end**: O fluxo de extração de dados do Cartão de Cidadão por IA e preenchimento automático não funcionava correctamente:
  - **cc_validity ignorado**: O campo `cc_validity` (validade do CC) era extraído pela IA mas fazia drop silencioso no `ProcessDetails.js`. Adicionado ao handler.
  - **Campos divergentes não aplicáveis**: Quando um campo já tinha valor na BD mas o documento mostrava valor diferente (ex: CC renovado), os dados eram exibidos mas impossíveis de aplicar. Agora `comparison.different` é incluído em `auto_fill_suggestions` com `type="override"`.
  - **Dados não persistiam no backend**: O callback `onAIDataExtracted` apenas actualizava React state, sem guardar na BD. Agora chama automaticamente `ai-apply-suggestions` quando não há conflitos.
  - **Conflitos nunca detectados**: A lógica de conflitos verificava `auto_fill_suggestions` (que só tinha campos vazios). Agora usa `comparison.different` para gerar conflitos reais.
  - **Campos em falta no endpoint apply**: Adicionados `entidade_empregadora`, `categoria_profissional`, `subsidiario_alimentacao` e `artigo_matricial` ao mapeamento do endpoint `apply_ai_suggestions`.
  - **Novo**: Botão "Usar valor do documento" nos campos divergentes do dialog de análise IA.
- **Mapeamento automático de pastas não movia ficheiros**: O endpoint `POST /organize/{processId}` apenas criava pastas no S3 e retornava contadores falsos, mas **nunca movia os ficheiros**. Corrigido para chamar `s3_service.rename_file()` e mover efectivamente cada ficheiro para a pasta correcta (IRS → Financeiros, CC → Identificação, Caderneta → Imóvel, etc.).
  - **source_path perdido**: O frontend tinha o S3 path dos ficheiros mas não o enviava para o endpoint de organização. Corrigido para juntar `source_path` em ambas as funções (`handleAIAnalysis` e `handleQuickOrganize`).
  - **Path sem `/` separador**: `s3_storage.py:move_file()` tinha bug `f"{client_folder}{target_folder}"` (sem `/`) — corrigido para `f"{client_folder}/{target_folder}"`.
  - **Mapeamento de pastas desalinhado**: O endpoint de organização usava sub-pastas (`Financeiros/IRS`, `Financeiros/Recibos`) que não correspondiam às categorias do S3. Unificado com `DOCUMENT_CATEGORIES` do `ai_document_analyzer.py` (pastas flat: Financeiros, Bancários, Imóvel, etc.).
- **Métrica de confiança da IA por campo**: Implementado sistema completo de confiança (0.0-1.0) por campo extraído:
  - **Prompt IA actualizado**: Agora retorna `confianca_campos` (confiança individual por campo) em vez de apenas confiança geral do documento. Instruções detalhadas para níveis: 1.0 (claro), 0.9 (legível), 0.8 (parcial), 0.7 (difícil), ≤0.5 (muito ilegível).
  - **Backend**: `analyze_multiple_documents` agora popula `field_confidence` mapando campos extraídos para campos do cliente, mantendo a maior confiança quando múltiplos documentos cobrem o mesmo campo.
  - **Frontend — ProcessDetails**: Campos com confiança < 0.8 ficam com borda amarela/vermelha e badge "IA XX%" no formulário (NIF, Documento CC, Data Nascimento, Validade CC). Toast de aviso lista campos com baixa confiança.
  - **Frontend — S3FileManager Dialog**: Campos no dialog de análise mostram badge de confiança (%). Campos < 0.8 ficam com fundo amarelo e aviso "⚠️ Baixa confiança — verifique manualmente".
  - A IA assiste em vez de substituir: dados com baixa confiança são destacados para revisão humana obrigatória.

## [2026-04-01] - Funcionalidades e Correções

### Adicionado
- **Auto-Rascunhos de E-mails por IA**: Sistema automático de geração de rascunhos de e-mails quando documentos em falta são detetados pela análise de IA. Inclui: toggle on/off via SystemConfig, 6 endpoints REST (CRUD de rascunhos + envio), tab "Rascunhos Pendentes" no StaffDashboard, integração com `analyze_multiple_documents()`, deduplicação por tipo de documento.
- **Sistema de Anotações Contextuais em Documentos**: Sistema completo de anotações em PDFs com 5 tipos (Nota, Questão, Aviso, Financeiro, Aprovação). Inclui: backend (modelo, serviço, 7 endpoints REST, índices MongoDB), frontend (PDFAnnotationViewer com pdfjs-dist ~1540 linhas, zoom, navegação, sidebar, filtros), integração com botão 🗨️ no S3FileManager (lista e grelha).
- **Trilhas de Auditoria (Audit Trails)**: Sistema completo de registo de auditoria que rastreia todas as alterações aos processos. Inclui: colecção MongoDB separada (`audit_trail`), IP tracking via headers, 4 origens (web, api, ai_automation, email), acompanhamento de aprovações/rejeições de IA, página admin com filtros avançados e exportação CSV, toggle on/off via SystemConfig, retenção configurável.

## [2026-04-01] - Correções e Melhorias

### Corrigido
- **AWS Secret Access Key visível na UI**: O campo `aws_secret_access_key` não estava na lista de campos sensíveis, fazendo com que o valor real fosse retornado em vez de ser mascarado. Adicionado à lista de campos sensíveis no backend (rotas e serviço de system_config).
- **Campos de password adicionados à lista de mascaragem**: Todos os campos de password foram adicionados à lista de campos sensíveis para mascaragem adequada na interface de configurações: `aws_secret_access_key`, `smtp_password_2`, `imap_password_2`, `hcpro_password`, `decisoes_password`, `doutorfinancas_password`, `custom_portal_password`.
- **Erros 403 DSTI / 404 send-documentation**: Investigação completa confirma que nenhum destes erros é originado pelo código atual do frontend. O cálculo DSTI é puramente client-side (DSTICalculator.js). O endpoint `POST /emails/send-documentation/{id}` existe corretamente em emails.py. Estes erros provavelmente resultam de cache do browser ou de uma versão antiga do frontend em produção (Render).

### Adicionado
- **Contador de Chamadas ao Agente IA**: Nova secção "Chamadas ao Agente IA" na página de Treino do Agente IA, mostrando:
  - Total de chamadas efectuadas (incrementado automaticamente a cada análise de documento)
  - Data e autor da última execução
  - O contador é persistido na colecção `ai_config` da MongoDB
  - Backend: `analyze_document_with_ai()` agora incrementa o contador a cada análise bem-sucedida
  - Backend: Endpoint existente `GET /api/admin/ai-training/stats` já fornecia os dados (a UI agora consome-os)
  - Backend: Endpoint existente `POST /api/admin/ai-training/prompt/execute` disponível para execução manual

## [2026-03-24] - Pré-visualização para Consultores e Correções de Build

### Nota
- **Quadro Origem dos Dados**: Visível apenas para o role ADMIN (por design)

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
