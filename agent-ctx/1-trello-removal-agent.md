# Task 1: Trello Removal Agent

## Task
Remove Trello integration completely from PowerCell (DEPRECATION removal)

## Summary
All Trello integration code has been completely removed from both backend and frontend.

## Files Deleted (5)
- `backend/routes/trello.py`
- `backend/services/trello.py`
- `backend/tests/integration/test_iteration14_trello_integration.py`
- `backend/tests/test_iteration16_leads_trello.py`
- `frontend/src/components/TrelloIntegration.js`

## Files Modified (16)

### Backend
1. `backend/server.py` - Removed trello router import, router registration, startup init call
2. `backend/config.py` - Removed TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID env vars
3. `backend/models/process.py` - Removed trello_card_id, trello_list_id fields
4. `backend/models/system_config.py` - Removed TrelloConfig class and trello field from SystemConfig
5. `backend/routes/processes.py` - Removed trello import, sync_process_to_trello function, 3 sync calls
6. `backend/routes/admin.py` - Removed Trello member auto-association logic (~30 lines)
7. `backend/routes/system_config.py` - Removed trello CONFIG_FIELDS section, test-connection handler, reveal-secrets refs
8. `backend/routes/diagnostics.py` - Removed check_trello_service function, all trello service references
9. `backend/services/system_config.py` - Removed TrelloConfig import, default config init, section handler
10. `backend/services/task_queue.py` - Removed sync_trello method and docstring references
11. `backend/worker.py` - Removed sync_trello task handler, trello lazy-loading references

### Frontend
12. `frontend/src/pages/SettingsPage.js` - Removed TrelloIntegration import and render
13. `frontend/src/pages/DiagnosticsPage.js` - Removed Trello icon import and service map entry
14. `frontend/src/pages/SystemConfigPage.js` - Removed Trello icon, section icon, test-connection filter, header comment
15. `frontend/src/pages/ProcessDetails.js` - Removed trello source badge
16. `frontend/src/services/api.js` - Removed getTrelloStatus and syncProcessWithTrello exports
17. `frontend/src/components/UnifiedAuditTrail.js` - Removed trello source badge

## Remaining References (non-functional, informational only)
- `backend/routes/admin.py` lines 950-951: Docstring mentioning Trello (marked as deprecated)
- `backend/routes/admin.py` lines 1496, 1548: Historical comments about Trello migration
- `backend/models/client.py` line 104: Comment listing "trello" as a possible source value
- Test files (test_iteration6.py, test_iteration13_duplicate_blocking.py): Old test references

## Verification
- Dev server running without errors
- No import errors from removed trello module
- No functional Trello code remains
