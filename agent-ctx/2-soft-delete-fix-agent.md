# Task 2: Fix Soft Delete gaps for Processes and Clients

## Summary
All 5 fixes have been applied successfully.

## Files Modified
1. **backend/routes/processes.py** — Added DELETE /{process_id} endpoint (line 3000)
2. **backend/routes/clients.py** — 3 fixes (is_deleted filters + cascade removal)
3. **backend/routes/admin.py** — Hard delete → soft delete

## Key Design Decisions
- Process deletion is now fully independent from client deletion
- Deleting a client only removes the client_id reference from processes
- All GET list endpoints now filter out soft-deleted records
- No more hard deletes for processes anywhere in the system
