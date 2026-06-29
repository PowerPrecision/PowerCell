# Task 5-6: Fix portal-requests 500 error and webmail folder sync

## Summary

### Task 1: Portal-Requests 500 Error
- **File**: `backend/routes/documents.py`
- **Changes**:
  1. Added request data logging at endpoint entry (process_id, category, notes, custom_label, user_id) for debugging
  2. Added process_id validation to reject empty/blank IDs with 400 error
  3. Enhanced outer except block to include input data in error log for post-mortem debugging
- **Assessment**: The endpoint already had good defensive structure (outer try/except, inner try/except for DB operations, uuid imported). The 500 errors were likely caused by unlogged exceptions where the input data was lost, making debugging impossible.

### Task 2: Webmail Sent/Drafts/Trash Folders
- **File**: `backend/services/email_service.py`
- **Changes**:
  1. `sync_webmail_emails` (global sync): Added explicit `em["direction"] = "sent"` for Sent folder emails
  2. `sync_user_emails` (user sync): Added explicit `em["direction"] = "sent"` for Sent folder emails
  3. `sync_shared_role_emails` (shared role sync): Added explicit `email_data["direction"] = "sent"` for Sent folder emails
- **Root cause**: The `_fetch_all_from_folder_sync` function infers direction by comparing `from_email == account.email`, which is unreliable (casing differences, aliases, etc.). This caused Sent emails to sometimes get `direction="received"` and appear in Inbox instead of Sent.
- **No frontend changes needed**: The WebmailPage.jsx already had all 5 folders in the sidebar, proper count fetching via webmail-stats API, and correct badge rendering.
- **No webmail-stats changes needed**: The endpoint already returns all 5 folder counts (inbox, sent, starred, drafts, trash).
