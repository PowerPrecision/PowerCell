---
Task ID: webmail-realtime-sync
Agent: main
Task: Webmail Real-Time Sync — Auto-sync em background + WebSocket NEW_EMAIL + Frontend reativo

Work Log:
- Analisou arquitetura atual: sync_webmail_emails(), sync_user_emails(), WebSocket manager, scheduled_tasks.py, server.py startup, WebmailPage.jsx
- Backend: Adicionou WSEventType.NEW_EMAIL ao websocket_manager.py (backend + frontend)
- Backend: Modificou sync_webmail_emails() em email_service.py para emitir evento NEW_EMAIL via WebSocket quando novo email é inserido na BD global (notifica admin/ceo/diretor/administrativo + utilizadores cujo email está nos destinatários + indexação)
- Backend: Modificou sync_user_emails() em email_service.py para emitir evento NEW_EMAIL diretamente ao dono da caixa pessoal
- Backend: Criou auto_sync_emails() e run_email_auto_sync() em scheduled_tasks.py — sincroniza caixa geral, pessoais e partilhadas a cada 3 minutos
- Backend: Registou run_email_auto_sync() como tarefa de background no startup do FastAPI (server.py)
- Frontend: Adicionou WSEventType.NEW_EMAIL ao useWebSocket.js
- Frontend: Adicionou handler onNewEmail ao useWebSocket.js
- Frontend: Em WebmailPage.jsx, adicionou hook useWebSocket com callback onNewEmail que:
  - Ação A: Mostra toast.info('📧 Novo email recebido de: [Remetente]')
  - Ação B: Faz refresh automático da lista de emails e contadores de pastas
- Commit 6678e0b pushed para origin/dev

Stage Summary:
- Webmail agora sincroniza automaticamente a cada 3 minutos (sem intervenção do utilizador)
- Novos emails detetados geram evento WebSocket NEW_EMAIL em tempo real
- Frontend atualiza pastas e mostra toast quando chegam novos emails
- Arquitectura de 3 camadas: Auto-sync → WebSocket → UI reativa
Agent: main
Task: RBAC Synchronization — 8 definitive profiles, centralized roleUtils, security rules

Work Log:
- Removed MEDIADOR and CONSULTOR_INTERMEDIARIO from UserRoleEnum in backend/models/auth.py
- Updated STAFF_ROLES, DOCUMENT_ROLES, MANAGEMENT_ROLES in auth.py to match 8 profiles
- Synced backend/models/enums.py with auth.py (removed MEDIADOR)
- Updated backend/services/permissions.py: removed mediador from DEFAULT_PERMISSIONS_BY_ROLE, updated role display labels
- Fixed backend/services/auth.py: require_roles hierarchy now uses INTERMEDIARIO instead of MEDIADOR
- Cleaned 13 backend route files of UserRole.MEDIADOR and UserRole.CONSULTOR_INTERMEDIARIO references
- Updated middleware/user_rate_limit.py, services/encryption.py, services/process_service.py
- Updated scripts/auto_assign_clients.py and scripts/assign_specific_clients.py
- Rewrote frontend/src/utils/roleUtils.js as comprehensive Single Source of Truth with:
  - VALID_ROLES, STAFF_ROLES, ADMIN_PANEL_ROLES, MANAGEMENT_ROLES, ADDITIONAL_ROLE_OPTIONS, PRIMARY_ROLE_OPTIONS
  - ROLE_LABELS (friendly: "Indexação de Dados", "Apoio Administrativo", etc.)
  - ROLE_COLORS, ROLE_SIDEBAR_COLORS, ROLE_ADDITIONAL_COLORS (Tailwind CSS)
  - ROLE_ICONS, ROLE_HIERARCHY
  - Permission functions: canAccessAdminPanel(), canManageUsers(), canSeeGestao(), isValidRole(), isStaff()
  - Deep role search utilities: hasRole(), hasAnyRole(), filterByRole(), etc.
- Updated UsersManagementPage.js:
  - Imports from roleUtils.js (no more local roleLabels/roleColors)
  - Dropdowns use PRIMARY_ROLE_OPTIONS for 8 profiles
  - Colored badges using ROLE_COLORS and ROLE_ADDITIONAL_COLORS
  - SECURITY RULE: role dropdowns and additional role checkboxes DISABLED for non-admin/CEO users
  - Filter dropdown uses STAFF_ROLES from roleUtils
- Updated DashboardLayout.js:
  - Imports ROLE_LABELS and ROLE_SIDEBAR_COLORS from roleUtils
  - INDEXAÇÃO now sees "Comunicações e Ficheiros" menu (was missing!)
  - Removed consultor_intermediario from consultor/intermediario menu check
- Updated ContextSwitcher.jsx: imports ROLE_LABELS and ROLE_ICONS from roleUtils
- Updated App.js: imports STAFF_ROLES from roleUtils, removed consultor_intermediario
- Cleaned 7 more frontend files of consultor_intermediario references
- Frontend build passes (npx vite build ✓)
- Backend Python syntax check passes
- Committed as da88c5a (push failed due to expired token)

Stage Summary:
- 8 definitive profiles enforced: admin, CEO, diretor, administrativo, consultor, intermediario, indexação, parceiro
- roleUtils.js is now the Single Source of Truth for RBAC in the frontend
- Indexação role now has access to "Comunicações e Ficheiros" menu
- Non-admin/CEO users cannot change roles (dropdowns disabled)
- All mediador/consultor_intermediario references cleaned from both backend and frontend
- Friendly labels: indexação → "Indexação de Dados", administrativo → "Apoio Administrativo"
