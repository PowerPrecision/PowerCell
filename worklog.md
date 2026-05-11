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

---
Task ID: 1
Agent: Main Agent
Task: Implement Playwright RPA engine for Portal das Finanças & Segurança Social

Work Log:
- Explored existing backend structure: portal.py (mock scrapers), S3 service, email service
- Installed playwright==1.59.0 and Chromium browser
- Created backend/services/gov_scraper.py with full Playwright async automation
- Implemented fetch_financas_documents(): Login via acesso.gov.pt, download IRS + Nota de Liquidação
- Implemented fetch_seg_social_documents(): Login via app.seg-social.pt, download docs
- Replaced mock scrapers in portal.py with real gov_scraper calls + S3 upload + DB records
- Fixed email service: replaced raw SMTP with main email service (Resend API) + fallback
- Added /portal/scraper-status diagnostic endpoint (requires portal auth)
- Conducted security audit, fixed all CRITICAL and HIGH issues:
  - Fixed _secure_clear_password no-op (now uses del password in caller scope)
  - Added try/finally to _financas_scraper_inner for browser cleanup
  - Fixed double-close risk in _seg_social_scraper_inner
  - Sanitized exception logging (type only, no credential leakage)
  - Removed --disable-web-security Chromium flag
  - Reduced NIF/NISS mask visibility (2 visible digits instead of 5)
  - Made /scraper-status require portal authentication
- Committed as 3c5cce1 on dev branch, pushed to origin/dev

Stage Summary:
- New file: backend/services/gov_scraper.py (949 lines, Playwright RPA)
- Modified: backend/routes/portal.py (replaced mock scrapers with real automation + S3 upload)
- Modified: backend/requirements.txt (added playwright==1.59.0)
- All security audit issues fixed (3 CRITICAL, 3 HIGH, 4 MEDIUM)
- Pushed to origin/dev: commit 3c5cce1

---
Task ID: 1
Agent: Main Agent
Task: Fix React error #310 in PermissionsTab.js and verify backend scraper implementation

Work Log:
- Diagnosed React error #310 ("Too many re-renders") in frontend
- Found root cause: PermissionsTab.js called useAuth() inside IIFE (violates Rules of Hooks)
- Fixed by: importing useAuth at top level and calling as proper React hook
- Verified backend scraper (gov_scraper.py) was already fully implemented in previous session
- Verified portal.py endpoints (fetch-financas, fetch-seguranca-social) were complete
- Verified playwright==1.59.0 already in requirements.txt
- Cherry-picked fix commit to dev branch and pushed to origin/dev

Stage Summary:
- React error #310 fix committed to origin/dev (447924b)
- Backend scraper engine (Playwright RPA) already implemented: fetch_financas_documents() + fetch_seg_social_documents()
- Portal routes with S3 upload, email notifications, team notifications already complete
- All changes pushed to origin/dev
