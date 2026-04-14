# Worklog - PowerCell CRM

---
Task ID: 5
Agent: Frontend Agent
Task: Implement Custom Folders UI in WebmailPage

Work Log:
- **Imports (line 65-71)**: Added 7 lucide-react icons: `FolderPlus, FolderOpen, Folder, FolderInput, Pencil, MoreVertical`. All existing imports preserved.
- **Custom folders state variables (line 200-209)**: Added 9 new state variables: `customFolders`, `activeCustomFolder`, `folderDialogOpen`, `folderDialogMode`, `folderDialogData`, `folderDialogSaving`, `moveFolderOpen`, `contextMenuPosition`, `contextMenuFolder`.
- **fetchCustomFolders (line 242-259)**: New `useCallback` fetching `GET /api/emails/folders` with auth. Returns `data.folders` array. `useEffect` on mount triggers fetch.
- **fetchEmails modified (line 264-283)**: Added 5th parameter `customFolderId`. When set, uses `folder: "custom"` and appends `custom_folder=<id>` query param.
- **useEffect updated (line 308-319)**: Now checks `activeCustomFolder` first — if set, calls `fetchEmails("custom", ...)` with folder ID. Added `activeCustomFolder` to dependency array.
- **handleSearchChange updated (line 321-335)**: Passes `activeCustomFolder` through to `fetchEmails` when in custom folder view.
- **handleRefresh updated (line 337-344)**: Same custom folder awareness as search.
- **handleSyncEmails updated (line 393-406)**: Refresh respects active custom folder after sync.
- **Folder CRUD handlers (line 807-918)**:
  - `handleOpenFolderDialog(mode, folder)`: Opens create/edit dialog with appropriate defaults.
  - `handleSaveFolder()`: POST/PUT to `/api/emails/folders`. Validates name, shows toast on success/error.
  - `handleDeleteFolder(folder)`: DELETE to `/api/emails/folders/{id}`. Resets `activeCustomFolder` if deleted folder was active.
  - `handleMoveToFolder(folderId)`: POST to `/api/emails/emails/move-to-folder`. Works with both selectedEmails (multi-select) and selectedEmail (single). Clears selection and refreshes.
- **Sidebar folders updated (line 1051-1060)**: System folder buttons now clear `activeCustomFolder(null)` on click. Active state checks both `!selectedLabel && !activeCustomFolder`.
- **Custom Folders sidebar section (line 1131-1199)**: New "Pastas" section after Marcadores, before footer. Shows FolderPlus button for creating. Lists custom folders with FolderOpen icon (colored when active), name, email_count badge, and hover-revealed MoreVertical context menu trigger.
- **List header title updated (line 1221-1244)**: Shows custom folder name when `activeCustomFolder` is set, with X button to deselect. Falls back to label name, then system folder name.
- **Move to Folder toolbar button (line 1017-1033)**: Visible in top bar when multi-select mode active and emails selected. Shows FolderInput icon, "Mover" label, and selected count badge.
- **Move to Folder in reading pane (line 1601-1612)**: Tooltip-wrapped FolderInput button in email detail action toolbar (alongside Reply, Forward, Star, Link).
- **Folder Context Menu (line 2039-2077)**: Absolutely positioned menu with fixed inset-0 backdrop for outside-click dismiss. "Renomear" opens edit dialog. "Eliminar" uses window.confirm before calling DELETE.
- **Folder Create/Edit Dialog (line 2079-2140)**: Dialog with name Input (Enter to submit) and 10 color swatches. Create mode: "Nova Pasta" title, POST. Edit mode: "Editar Pasta" title, PUT.
- **Move to Folder Dialog (line 2142-2179)**: Dialog listing "Caixa de Entrada" + all custom folders. Click to move. Shows email count per folder.

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/WebmailPage.jsx` (1761 → 2186 linhas, +425)
- Vite build OK, sem erros
- Todas as funcionalidades existentes preservadas (labels, multi-select, composer, sync, etc.)
- Todo o texto em português
- APIs consumidas: GET/POST/PUT/DELETE /api/emails/folders, POST /api/emails/emails/move-to-folder, GET /api/emails/webmail?folder=custom&custom_folder=...

---
Task ID: 2
Agent: Backend Agent
Task: Create Custom Email Folders backend system

Work Log:
- Added FolderCreateRequest and FolderUpdateRequest Pydantic models
- Added GET /folders, POST /folders, PUT /folders/{id}, DELETE /folders/{id} endpoints
- Added POST /emails/move-to-folder endpoint for moving emails
- Updated webmail_list to support custom_folder query parameter
- All endpoints follow existing patterns with auth, sanitization, validation

Stage Summary:
- email_folders MongoDB collection used for custom folders
- folder_id field on emails references custom folders
- Folder deletion removes folder_id from emails (back to inbox)
- Folder counts returned via aggregation pipeline

---
Task ID: 2-b
Agent: Frontend Agent
Task: Refactor WebmailPage.jsx — Labels Sidebar, Multi-Select, Attachment Cards, Drag & Drop

Work Log:
- **Imports (line 57-72)**: Added lucide-react icons: `Image, FileSpreadsheet, File, Tag, CheckSquare, Square, Upload, Download, Trash2`. All existing imports preserved.
- **Utility functions (line 111-130)**: Added `formatFileSize(bytes)` — formats bytes as B/KB/MB. Added `getAttachmentIcon(filename)` — returns appropriate icon based on file extension (Image for images, FileSpreadsheet for sheets, FileText for docs, File for others).
- **New state variables (line 178-192)**:
  - Labels: `labels`, `selectedLabel`, `labelsLoading`
  - Multi-select: `selectedEmails` (Set), `multiSelectMode`, `labelDropdownOpen`
  - Upload: `uploadAttachments`, `uploadingFiles`
  - `fileInputRef` (useRef for hidden file input)
- **fetchLabels (line 200-222)**: New `useCallback` fetching `GET /api/emails/labels` with auth. Handles array and object responses gracefully. `useEffect` on mount calls `fetchLabels()`.
- **fetchEmails modified (line 248-261)**: Added `label` parameter to `fetchEmails`. When `selectedLabel` is set, appends `label=<label_id>` to query params. All callers updated: `useEffect`, `handleSearchChange`, `handleRefresh`, `handleSyncEmails`.
- **handleSelectEmail modified (line 353-358)**: In multi-select mode, clicking an email toggles its ID in `selectedEmails` Set instead of opening reading pane.
- **handleSendEmail modified (line 505-512)**: Includes `attachment_ids: uploadAttachments.map(a => a.id)` in request body when uploads exist.
- **openComposer modified (line 447)**: Clears `uploadAttachments` when opening composer.
- **Multi-select handlers (line 618-690)**:
  - `handleToggleMultiSelect`: Toggles mode, clears selection on exit.
  - `handleSelectAll`: Selects/deselects all emails on current page.
  - `handleApplyLabelToSelected`: POST to `/api/emails/labels/apply` with `email_ids` + `label_id`.
  - `handleDeleteSelected`: Deletes all selected emails via parallel DELETE calls.
- **File upload handlers (line 694-745)**:
  - `uploadFiles(files)`: Sequential upload via `POST /api/emails/attachments/upload` with FormData.
  - `handleDropZoneClick`, `handleFileInputChange`, `handleDragOver`, `handleDrop`: Drag & drop event handlers.
  - `handleRemoveUpload`: Removes file from `uploadAttachments` list.
- **Labels sidebar (line 913-946)**: "Marcadores" section below FOLDERS nav. Shows colored circle + label name for each label. Click selects label (highlights, filters list). Click again deselects.
- **Label badges on email list (line 1088-1102)**: After preview text, renders up to 2 colored label pills per email. Shows "+N" badge if more than 2. Uses `backgroundColor: label.color`, white text, 10px font, rounded-full.
- **Label badges on email detail (line 1295-1308)**: Below date meta, shows all label badges.
- **Multi-select toolbar button (line 812-824)**: "Selecionar" toggle button next to Refresh. Shows CheckSquare (active) or Square (inactive).
- **Multi-select checkboxes (line 1058-1065, 1069-1072)**: When `multiSelectMode` is active, shows CheckSquare/Square icon instead of unread dot on each email row.
- **Floating action bar (line 1429-1478)**: Fixed bottom bar when emails selected. Shows count, "Aplicar Marcador" button with label dropdown, "Eliminar" button.
- **Attachment cards in reading pane (line 1360-1405)**: Replaced plain list with grid of visual cards. Each card shows: file type icon (via getAttachmentIcon), filename, formatted size, download button. Grid: 1 column mobile, 2 columns sm+.
- **Drag & drop zone in composer (line 1566-1638)**: Dashed-border drop zone before Textarea. Hidden file input with `multiple`. Drag & drop events handled. Upload progress indicator (Loader2 spinner). Uploaded files shown as removable cards with icon, name, size, X button.
- **Dialog cleanup (line 1544-1551)**: `onOpenChange` clears `uploadAttachments` when dialog closes.

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/WebmailPage.jsx` (1238 → 1761 linhas, +523)
- 6 funcionalidades adicionadas ao webmail
- Todas as APIs chamadas com try/catch — falhas silenciosas para endpoints ainda não disponíveis
- Layout 3 colunas intacto, responsivo
- Todo o texto em português

---
Task ID: 2-a
Agent: Backend Agent
Task: Implement Backend - Email Labels CRUD + S3 Attachment Upload/Download

Work Log:
- **`backend/models/email.py`**: Adicionados 3 modelos Pydantic:
  - `LabelCreateRequest` (name, color) — payload para criar labels
  - `LabelUpdateRequest` (name?, color?) — payload para atualizar labels
  - `EmailSendRequest.attachment_ids: Optional[List[str]] = None` — campo opcional para IDs de anexos temporários
- **`backend/routes/emails.py`**: Adicionados 7 novos endpoints e 1 endpoint modificado:
  - **GET /labels** (line 928): Lista todas as labels do utilizador. Faz seed de 5 labels predefinidas (Urgente, A Aguardar, Concluído, Follow-up, Reunião) na primeira chamada.
  - **POST /labels** (line 956): Cria nova label. Valida nome (max 30 chars), cor (hex), impede duplicados.
  - **PUT /labels/{label_id}** (line 990): Atualiza nome e/ou cor de label existente. Valida duplicados (excluindo a própria).
  - **DELETE /labels/{label_id}** (line 1026): Elimina label e remove-a de todos os emails via `$pull`.
  - **POST /attachments/upload** (line 1054): Upload de 1-10 ficheiros (max 25MB cada) para `temp/attachments/{user_id}/{uuid}_{filename}` no S3. Guarda metadados em `temp_attachments` (MongoDB) para lookup durante envio.
  - **GET /{email_id}/attachments/{file_id}/download** (line 1138): Gera URL pré-assinada (1h) para download de anexo via `s3_service.get_presigned_url()`. Suporta fallback para URL existente.
  - **POST /send** modificado (line 2122): Processa `attachment_ids` — consulta `temp_attachments`, descarrega conteúdo do S3 temp, envia email com anexos, move ficheiros para `Emails/{email_id}/{filename}` via `s3_service.rename_file()`, atualiza documento do email com `id`, `s3_key` nos attachments, limpa temp do S3 e MongoDB.
- **Imports adicionais**: `UploadFile, File, Form` (FastAPI), `re` (validação de hex color), `LabelCreateRequest, LabelUpdateRequest` (modelos).
- **Helper**: `_validate_hex_color()` — valida formato `#fff` ou `#ffffff`.

Stage Summary:
- 2 ficheiros alterados: `backend/models/email.py` (+20), `backend/routes/emails.py` (+240)
- 7 novos endpoints: 4 labels CRUD + 1 upload + 1 download + 1 send modificado
- Rotas estáticas todas definidas ANTES do catch-all `/{email_id}`
- Syntax verificado com py_compile: OK
- Coleções MongoDB utilizadas: `email_labels` (labels CRUD), `temp_attachments` (upload temporário)

---
Task ID: 14
Agent: Main Agent
Task: SmartRichEditor — abstrair complexidade HTML de utilizadores não-admin

Work Log:
- **SmartRichEditor.jsx** (`2c85c79`): Novo componente reutilizável (`src/components/ui/SmartRichEditor.jsx`)
  - Modo Visual (default): Editor WYSIWYG via react-quill — edição normal
  - Modo HTML (admin-only): `<textarea>` monospace com código HTML puro
  - Botão `</> Editar HTML` no canto superior direito — **SÓ visível se `user.role === 'admin'`**
  - Consultores nunca veem o botão nem sabem que o modo HTML existe
  - Props: `value`, `onChange`, `readOnly`, `advanced`, `minHeight`, `label`, `placeholder`, `allowHtmlAdmin`
  - Protege variáveis {{handlebars}} ao transitar entre modos
- **SendDocumentationModal.js** (`2c85c79`): Substituído sistema de 3 tabs (Preview / Editar HTML / Código) por 2 tabs (Preview / Editar)
  - Tab "Editar" usa SmartRichEditor internamente com toggle HTML integrado
  - Tab "Código" e botão "Copiar HTML" removidos (funcionalidade agora dentro do SmartRichEditor)
  - Texto informativo contextual baseado no role do utilizador
  - Limpos imports não utilizados (`Code`, `RichTextEditor` direct)
- **SystemConfigPage.js** (`2c85c79`): Substituído RichTextEditor + pré-visualização separada por SmartRichEditor único
  - Secção "Pré-visualização" redundante removida (o modo visual já é a preview)
  - Limpo import de `RichTextViewer` (já não usado nesta página)

Stage Summary:
- 3 ficheiros alterados: `SmartRichEditor.jsx` (novo), `SendDocumentationModal.js`, `SystemConfigPage.js`
- Commit: `2c85c79` (pushed to `dev`)

---
Task ID: 13
Agent: Main Agent
Task: Corrigir erro "too many values to unpack" na sincronização de emails (resolução final)

Work Log:
- **Diagnóstico (`086c502`)**: Após 3 tentativas falhadas de corrigir `mail.fetch()` unpacking, identificou-se a causa REAL:
  - O erro NUNCA foi no `mail.fetch()` — era na linha 1331 de `email_service.py`
  - `get_email_body_with_embedded_images(msg)` retorna **3 valores** `(body_text, body_html, embedded_images)`
  - O código fazia unpack para apenas **2 variáveis**: `body_text, body_html = get_email_body_with_embedded_images(msg)`
  - Isto causava `too many values to unpack (expected 2)` para CADA email, e o `except` fazia `continue` — nenhum email era guardado
- **Correção (`086c502`)**: Alterado para `body_text, body_html, _ = get_email_body_with_embedded_images(msg)`
- **Cleanup (`086c502`)**: Removida função `_extract_email_bytes_from_fetch` duplicada (havía 2 definições idênticas, linhas 251-276 e 300-315)
- **Histórico de tentativas anteriores** (commits já no remote):
  - `54143d1`: Corrigiu apenas 1 de 6 localizações (insuficiente)
  - `8bef4b2`: Criou helper `_extract_email_bytes_from_fetch()`, substituiu todas as 6 localizações (mas o bug era noutro lado)
  - `3976603`: Reforço da mesma correção (commit duplicado)

Stage Summary:
- 1 ficheiro alterado: `backend/services/email_service.py` (+1, -19)
- O bug explicava por que 29 emails eram encontrados mas 0 eram guardados
- Commit: `086c502` (pushed to `dev`)

---
Task ID: 12
Agent: Main Agent
Task: Corrigir sincronização webmail — credenciais IMAP, 404, NoneType alerts

Work Log:
- **Alerts NoneType (`f48f4bb`)**: Erro `'NoneType' object has no attribute 'get'` em `services/alerts.py`
  - Causa: MongoDB campos set to `null`; `.get("key", {})` não aplica default quando valor é `None`
  - Correção: `process.get("credit_data") or {}` em vez de `process.get("credit_data", {})`
  - Mesma correção aplicada a `property_data`, `financial_data`, `contacto`
- **Webmail sync 404 (`fab2ef9`)**: `POST /api/emails/webmail/sync` retornava 404
  - Causa: `emails.py`, `email_service.py`, `worker.py` tinham alterações locais nunca commitadas ao Git
  - `git push` dizia "Everything up-to-date" porque nada estava staged
  - Correção: `git add` + `git commit` dos 3 ficheiros
- **IMAP credenciais erradas (`83f104d`)**: Emails não sincronizavam para `flaviosilva@powerealestate.pt`
  - Causa: `get_email_accounts_async()` usava `smtp_user`/`smtp_password` para login IMAP
  - O modelo de dados tem campos dedicados `imap_user`/`imap_password`
  - Correção: Alterado para usar `imap_user`/`imap_password` com fallback para SMTP
- **IMAP fetch format (`54143d1`, `8bef4b2`, `3976603`)**: "too many values to unpack"
  - Tentativas múltiplas de corrigir `mail.fetch()` (ver Task ID 13 para resolução final)

Stage Summary:
- Ficheiros: `backend/services/alerts.py`, `backend/routes/emails.py`, `backend/services/email_service.py`
- Commits: `f48f4bb`, `fab2ef9`, `83f104d`, `54143d1`, `8bef4b2`, `3976603`, `086c502`

---
Task ID: 11
Agent: Main Agent
Task: Webmail de 3 colunas (estilo Outlook) com compositor e sincronização IMAP

Work Log:
- **WebmailPage.jsx (`fcb858b`)**: Criada página de webmail completo com layout 3 colunas (estilo Outlook)
  - Coluna esquerda: Lista de pastas (INBOX, Enviados, Rascunhos, Lixo, Spam) com contadores
  - Coluna central: Lista de emails da pasta selecionada (remetente, assunto, preview, data, indicadores)
  - Coluna direita: Painel de leitura com corpo HTML, ações (responder, encaminhar, eliminar, arquivo)
  - Compositor de emails: Formulário modal com To, CC, CC0, Assunto, Body (RichText), Anexos
  - Pesquisa de emails por texto
  - Filtros: Todos / Não lidos / Com estrela
  - Marcação de lido/não lido, estrela, eliminação, arquivo
  - Suporte a contas múltiplas (Power + Precision)
- **Sync button (`041799b`)**: Adicionado botão "Sincronizar" no sidebar para puxar emails do IMAP
- **Endpoint webmail sync (`fab2ef9`)**: `POST /api/emails/webmail/sync` — sincroniza todas as contas IMAP
  - Busca emails de INBOX e pastas de enviados
  - Deduplicação por `message_id + account`
  - Guarda no MongoDB com metadata completa
- **Endpoints de webmail (`fcb858b`)**: CRUD completo
  - `GET /api/emails/webmail` — lista com filtros (folder, account, search, unread, starred)
  - `GET /api/emails/webmail/:id` — detalhe
  - `PUT /api/emails/webmail/:id` — atualizar (read, starred, archived, folder)
  - `DELETE /api/emails/webmail/:id` — eliminar
  - `POST /api/emails/webmail/send` — enviar email via SMTP
- **S3FileManager fix (`fdbb4a4`)**: Impedir eliminação de pastas no gestor de ficheiros S3

Stage Summary:
- Página de webmail completa com funcionalidades de email profissional
- Integração IMAP (leitura) e SMTP (envio)
- Commits: `fcb858b`, `041799b`, `fab2ef9`, `8e6604b`, `85a2d79`, `abf8ca5`

---
Task ID: 10
Agent: Main Agent
Task: Corrigir eliminação acidental de pastas no S3FileManager

Work Log:
- **S3FileManager fix (`fdbb4a4`)**: Adicionada validação para impedir eliminação de pastas (diretórios)
  - Tipos de ficheiro sem extensão (pastas) não podem ser eliminados
  - Apenas ficheiros com extensão podem ser removidos

Stage Summary:
- 1 ficheiro alterado
- Commit: `fdbb4a4`

---
Task ID: 9
Agent: Main Agent
Task: Remover menu Novo processo, corrigir filtro clientes, statusFilter default, alertas IA

Work Log:
- **Task 1 - Remover "Novo processo"**: Não existia menu no sidebar. Removido atalho `Ctrl+N` ("Novo processo/tarefa") do `useKeyboardShortcuts.js` e handler `onNew` do `DashboardLayout.js`.
- **Task 2 - Corrigir filtro clientes**: O backend aplicava `limit=500` à query de PROCESSOS (não clientes), o que fazia com que alguns clientes desaparecessem. Removido `skip/limit` da query MongoDB e aplicada paginação ao resultado final (lista de clientes únicos).
- **Task 3 - statusFilter default "active"**: Alterado `ClientsPage.js` de `|| "all"` para `|| "active"`.
- **Task 4 - Desativar alertas de consultor não atribuído**: Removido alerta `"unassigned"` e sugestão `"assignment"` do `ai_improvement_agent.py`. Processos sem consultor já não geram alertas no Agente de Melhoria IA.
- Commit: `a90e92f`, build OK, push OK.

Stage Summary:
- 5 ficheiros alterados, 14 inserções, 31 remoções
- Files: useKeyboardShortcuts.js, DashboardLayout.js, ClientsPage.js, clients.py, ai_improvement_agent.py

---
Task ID: 8
Agent: Main Agent
Task: Botões Simular Preenchimento + Testar Submissão em formulários

Work Log:
- **ProcessDetails.js (`4afe7fc`)**: Adicionados SIMULATE_DATA (5 state objects) + 2 botões:
  - `handleSimulateFill()`: preenche personal, titular2, financial, realEstate, credit com dados de teste
  - `handleSimulateAndTestSubmit()`: preenche + envia PUT ao backend para validar Pydantic
  - Botão "Simular Preenchimento" (ícone FlaskConical, cor amber) — preenche sem guardar
  - Botão "Testar Submissão" (ícone Play, cor emerald) — preenche + submete + mostra erros traduzidos
  - Após test submit com falha, mostra lista de erros Pydantic traduzidos em português
  - Após test submit, faz refetch para reverter dados ao estado original do servidor
  - Ambos desabilitados quando `saving`, `simulating` ou `isProcessLocked`
- **PublicClientForm.js (`4afe7fc`)**: Adicionado botão "Testar Submissão" ao lado de "Simular Preenchimento"
  - Usa `validateForm()` existente para validação client-side
  - Mostra lista de erros ou toast de sucesso
- Commits: `4afe7fc` (pushed to `dev`)

Stage Summary:
- 2 ficheiros alterados: `ProcessDetails.js` (+283 linhas), `PublicClientForm.js` (+27 linhas)
- Teste de submissão cobre validação client-side (PublicClientForm) e backend Pydantic (ProcessDetails)
- Dados de teste incluem NIF válido (checksum OK), datas reais, e todos os campos opcionais preenchidos

---
Task ID: 7
Agent: Main Agent
Task: Fix Vercel MIME type crash and MyClientsPage JSX errors

Work Log:
- **Vercel MIME type crash (`dbfab8a`)**: Analisado erro `'text/html' is not a valid JavaScript MIME type` no ProtectedRoute. Causa: `vercel.json` rewrite `"/(.*)"` interceptava pedidos a chunks JS (`/assets/StaffDashboard-*.js`) e retornava `index.html`. Corrigido com negative lookahead: `/((?!assets|_next|favicon\.ico|robots\.txt|manifest\.json|sw\.js|workbox-|icon-.*\.png).*)`.
- **LazyChunkErrorBoundary updated (`dbfab8a`)**: Adicionados 4 patterns ao error detector: `text/html`, `MIME type`, `Unexpected token`, `Script error`. Agora stale deployments causam reload automático em vez de crash.
- **MyClientsPage JSX error (`fd84f29`)**: Analisado Vercel build errors — 5 erros cascata de JSX tag mismatch. Causa: `</div>` orfão na linha 274 (dentro do Card de filtros). Removida a tag extra. Estrutura corrigida: `Card > CardContent > div.flex > conditional p > /CardContent > /Card`.
- Commits: `dbfab8a`, `fd84f29` (pushed to `dev`)

Stage Summary:
- 2 ficheiros alterados: `frontend/vercel.json`, `frontend/src/App.js`, `frontend/src/pages/MyClientsPage.js`
- Vercel build deve passar — rewrites não interceptam assets, JSX válido

---
Task ID: 6
Agent: Main Agent
Task: Fix 429 rate limiting cascade and StatisticsPage crash

Work Log:
- **API Interceptor retry (`4268eec`)**: Adicionado retry com exponential backoff no `api.js`:
  - 3 tentativas para 429 responses
  - Delays: 2s → 4s → 8s + jitter (±500ms)
  - Respeita header `Retry-After` se presente
  - Suprime toast de erro durante retries
  - Retry-ID header para tracking
- **NotificationsDropdown backoff (`4268eec`)**: Polling com backoff adaptativo:
  - 30s → 60s → 120s → 300s (max) em caso de 429
  - Reset após 3 sucessos consecutivos
- **StatisticsPage crash (`97bfed9`)**: `X.filter is not a function`:
  - API retorna `{'items': [], 'total': 0}` (paginado) mas frontend chamava `.filter()` no objeto
  - Adicionados `Array.isArray()` guards em `processes`, `leadsStats.funnel_data`, `leads_by_source`, `top_consultors`
  - `getStats()` faz fallback para `{}`
- Commits: `4268eec`, `97bfed9` (pushed to `dev`)

Stage Summary:
- 2 ficheiros alterados: `frontend/src/services/api.js`, `frontend/src/pages/StatisticsPage.js`
- Resiliência a 429 em 2 níveis (interceptor + polling)
- StatisticsPage defensivo contra respostas não-array

---
Task ID: 5
Agent: Main Agent
Task: 4 áreas de melhorias de UX no frontend

Work Log:
- **TASK 1a - AuditTrailPage DashboardLayout**: Adicionado import de DashboardLayout e envolvido o conteúdo com `<DashboardLayout title="Auditoria">`. Removido padding duplicado.
- **TASK 1b - Sidebar accordion fix**: Corrigido `onOpenChange` com `e.stopPropagation()`. Adicionadas rotas em falta ao `getInitialOpenSections()`.
- **TASK 2 - Rich Text Editor RGPD**: Substituído `<Textarea>` por `<RichTextEditor>` com `readOnly`. Pré-visualização com `RichTextViewer`.
- **TASK 3 - Kanban 2nd Proponent Indicator**: Detecção de 2º proponente, borda lateral, badge.
- **TASK 4a - Tasks Panel reposicionado**: Movido para coluna direita (sidebar).
- **TASK 4b - RGPD confirmation dialog**: `window.confirm()` antes de enviar email.
- **TASK 4c - Magic Link Portal Button**: Popover com copiar link / enviar por email.
- Commit: `abd988e`

Stage Summary:
- 7 ficheiros alterados, 147 inserções, 30 remoções
- Files: AuditTrailPage.js, DashboardLayout.js, SystemConfigPage.js, KanbanCard.jsx, ProcessDetails.js, api.js

---
Task ID: 4
Agent: Main Agent
Task: Fix CI pipeline issues (pytest, submodules, Node.js)

Work Log:
- **pytest.ini multiline**: Removida continuação com backslash que causava parsing error. Commit: `9de712b`
- **Ghost submodule**: Removido `PowerCell` submodule fantasma do git index. Commit: `2e232ad`
- **Node.js 24**: Re-habilitado nos GitHub Actions. Commit: `6c6cb65`
- **Backend tests**: Adaptados para resposta paginada `{'items': [], 'total': 0}`. Commit: `1e63fac`
- **Async loop**: Resolvido `Future attached to a different loop`. Commit: `f84765d`

Stage Summary:
- CI pipeline estável com Node.js 24 + Python 3.11
- Todos os testes passam sem MongoDB

---
Task ID: 3
Agent: Main Agent
Task: Implementar Pipeline CI/CD com GitHub Actions

Work Log:
- Criado `.github/workflows/ci.yml` com pipeline completo
- Job 1 - Frontend CI (React + Vite): ESLint + Vite build
- Job 2 - Backend CI (Python + FastAPI): Flake8 + Pytest
- Job 3 - Notify on Failure (preparado para Slack/Teams)
- Criado backend/.flake8 com configuração
- Atualizado conftest.py com DUMMY_ENV_VARS

Stage Summary:
- CI Pipeline: Proteção contra código partido em produção
- Frontend: Build Vite como gatekeeper rigoroso
- Backend: Linting + Testes com env vars dummy

---
Task ID: 2
Agent: Main Agent
Task: Refatoração para TanStack Query (React Query v5)

Work Log:
- Instalado @tanstack/react-query e @tanstack/react-query-devtools
- Criado `lib/queryClient.js` com configuração otimizada
- Criado sistema de Query Keys Factory
- Criados hooks de Queries (useKanbanQuery, useProcessQuery, etc.)
- Criados hooks de Mutations (useMoveProcessMutation com optimistic update)
- Criado useKanbanRealtime para WebSocket + React Query
- Atualizado App.js com QueryClientProvider
- Refatorado KanbanBoard.js: eliminado useEffect/useState esparguete

Stage Summary:
- TanStack Query configurado com padrões CRM
- Optimistic updates e invalidação automática
- WebSocket integrado com setQueryData

---
Task ID: 1
Agent: Main Agent
Task: Implementar Motor de Tarefas Assíncronas e Centro de Operações Global

Work Log:
- Criado modelo TaskLog no MongoDB
- Criado serviço de gestão de tarefas (CRUD completo)
- Criadas rotas API (5 endpoints REST)
- Refatorado endpoint de AI para análise assíncrona (202 Accepted)
- Criado contexto React (TasksContext) com polling inteligente
- Criado componente TasksDropdown com badge e drawer
- Integrado no App.js e DashboardLayout.js

Stage Summary:
- Backend: Motor de tarefas assíncronas completo
- Frontend: Centro de Operações com polling
- Build compilado com sucesso

---
Task ID: 2
Agent: Backend WebSocket Agent
Task: Add PROCESS_MOVED, PROCESS_LOCKED, PROCESS_UNLOCKED WebSocket events

Work Log:
- Added PROCESS_MOVED, PROCESS_LOCKED, PROCESS_UNLOCKED to WSEventType
- Added sender-excluded PROCESS_MOVED broadcast in kanban move endpoint
- Added inbound LOCK/UNLOCK message handling in websocket route

Stage Summary:
- Backend broadcasts granular move events with user info
- Frontend can send lock/unlock events via WebSocket

---
Task ID: 1
Agent: Frontend Agent
Task: Replace textarea with react-quill WYSIWYG for email template

Work Log:
- Added 'react-quill-new/dist/quill.snow.css' import at top of DocumentRecipientsManager.js
- Replaced plain Textarea with ReactQuill snow theme component
- Configured toolbar with formatting buttons (headers, bold, italic, lists, align, link, clean)
- Added matching formats array for proper rendering

Stage Summary:
- Email template editor in System Config > Destinatários now uses visual WYSIWYG
- HTML is generated and stored in state as before

---
Task ID: 2
Agent: General Agent
Task: Add "Pré-visualizar RGPD" button with preview modal to SystemConfigPage.js

Work Log:
- **Dialog import (line 27)**: Added `import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog"`. Deduplicated a previously existing duplicate import.
- **State variable (line 1125)**: Added `const [showRgpdPreview, setShowRgpdPreview] = useState(false)` inside RGPDTab component.
- **Preview button (line 1343-1349)**: Added "👁️ Pré-visualizar RGPD" button with `variant="outline"` between "Restaurar Padrão" and "Guardar Template" buttons in the action bar.
- **Preview Dialog (line 1370-1399)**: Added Dialog component before `</CardContent>` with:
  - `sm:max-w-[700px] max-h-[85vh] overflow-y-auto` for responsive scrollable modal
  - `prose prose-sm` classes for nice typography on preview content
  - `dangerouslySetInnerHTML` with `.replace()` chains for all template variables (`{{NOME_CLIENTE}}`, `{{NOME_EMPRESA}}`, `{{CONTRIBUINTE}}`, `{{MORADA}}`, `{{CODIGO_POSTAL}}`, `{{TIPO_DOCUMENTO}}`, `{{NUMERO_DOCUMENTO}}`, `{{VALIDADE_DOCUMENTO}}`, `{{DATA_ASSINATURA}}`)
  - Realistic sample values (João Silva, Power Real Estate, 123456789, etc.)
  - Dynamic date via `new Date().toLocaleDateString("pt-PT")`
  - "Fechar" button in DialogFooter

Stage Summary:
- 1 ficheiro alterado: `frontend/src/pages/SystemConfigPage.js`
- Duplicate Dialog import cleaned up
- Preview modal fully functional with template variable substitution
- No changes to SmartRichEditor or existing functionality
