"""Admin routes — thin FastAPI stubs. Logic in services/admin_*.py."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import require_roles, get_current_user
from services.admin_helpers import _safe_float, _audit_log  # re-export if needed
from services.admin_permissions import CapabilityUpdateRequest
from services.admin_dev_ops import SyncDatabaseRequest, SeedRequest

from services.admin_permissions import (
    run_get_available_permissions,
    run_get_capabilities_grouped,
    run_get_capabilities_registry,
    run_get_default_permissions,
    run_get_default_permissions_for_role,
    run_get_user_permissions,
    run_reset_user_permissions,
    run_update_role_defaults,
    run_update_user_permissions,
)

from services.admin_workflow import (
    run_create_workflow_status,
    run_delete_workflow_status,
    run_fix_duplicate_workflow_statuses,
    run_get_workflow_statuses,
    run_migrate_portal_labels,
    run_s3_cors_diagnostic,
    run_update_workflow_status,
)

from models.user_company_role import UserRoleAssignBody
from services.user_company_roles_api_crud import (
    run_assign_user_company_role,
    run_delete_user_company_role,
    run_list_user_company_roles,
)
from services.admin_users import (
    run_admin_get_user_email_config,
    run_admin_set_user_email_config,
    run_admin_test_user_email_config,
    run_bulk_update_notification_preferences,
    run_create_user,
    run_delete_user,
    run_get_all_notification_preferences,
    run_get_notification_preferences,
    run_get_users,
    run_impersonate_user,
    run_stop_impersonate,
    run_update_notification_preferences,
    run_update_user,
)

from services.admin_process_ops import (
    run_fix_duplicate_processes,
    run_migrate_process_numbers,
    run_sync_process_emails,
    run_update_process_active_status,
)

from services.admin_ai_data import (
    run_add_ai_training_entry,
    run_bulk_resolve_ai_import_logs,
    run_delete_ai_training_entry,
    run_get_ai_import_log_detail,
    run_get_ai_import_logs,
    run_get_ai_import_logs_grouped,
    run_get_ai_import_logs_v2,
    run_get_ai_training_data,
    run_get_ai_training_prompt,
    run_get_ai_training_stats,
    run_record_ai_prompt_execution,
    run_resolve_ai_import_log,
    run_update_ai_training_entry,
)

from services.admin_observability import (
    run_bulk_resolve_system_errors,
    run_cancel_stuck_job,
    run_cleanup_old_error_logs,
    run_cleanup_old_jobs,
    run_cleanup_old_system_logs,
    run_delete_client_registration,
    run_get_audit_logs,
    run_get_client_registration,
    run_get_client_registrations_stats,
    run_get_jobs_health,
    run_get_stale_processes,
    run_get_system_error_logs,
    run_get_system_log_detail,
    run_get_system_logs_stats,
    run_get_team_performance,
    run_list_client_registrations,
    run_mark_errors_as_read,
    run_resolve_all_system_errors,
    run_resolve_system_error,
    run_update_client_registration,
)

from services.admin_dev_ops import (
    run_drop_specific_index,
    run_get_database_indexes,
    run_get_sync_status,
    run_repair_database_indexes,
    run_seed_realistic_data,
    run_sync_database,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/permissions/available")
async def get_available_permissions(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_get_available_permissions(user)


@router.get("/permissions/defaults")
async def get_default_permissions(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_get_default_permissions(user)


@router.get("/permissions/defaults/{role}")
async def get_default_permissions_for_role_endpoint(
    role: str, 
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_default_permissions_for_role(role, user)


@router.post("/users/{user_id}/reset-permissions")
async def reset_user_permissions(
    user_id: str, 
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_reset_user_permissions(user_id, user)


@router.get("/permissions/capabilities")
async def get_capabilities_registry(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_capabilities_registry(user)


@router.get("/permissions/capabilities/by-category")
async def get_capabilities_grouped(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_capabilities_grouped(user)


@router.put("/permissions/role-defaults/{role}")
async def update_role_defaults(
    role: str,
    request: CapabilityUpdateRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_update_role_defaults(role, request, user)


@router.get("/permissions/user/{user_id}")
async def get_user_permissions(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_user_permissions(user_id, user)


@router.put("/permissions/user/{user_id}")
async def update_user_permissions(
    user_id: str,
    request: CapabilityUpdateRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_update_user_permissions(user_id, request, user)


@router.get("/workflow-statuses", response_model=List[WorkflowStatusResponse])
async def get_workflow_statuses(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INDEXACAO, UserRole.INTERMEDIARIO, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))):
    return await run_get_workflow_statuses(user)


@router.post("/workflow-statuses", response_model=WorkflowStatusResponse)
async def create_workflow_status(data: WorkflowStatusCreate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_create_workflow_status(data, user)


@router.put("/workflow-statuses/{status_id}", response_model=WorkflowStatusResponse)
async def update_workflow_status(status_id: str, data: WorkflowStatusUpdate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_update_workflow_status(status_id, data, user)


@router.delete("/workflow-statuses/{status_id}")
async def delete_workflow_status(status_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_delete_workflow_status(status_id, user)


@router.post("/workflow-statuses/fix-duplicates")
async def fix_duplicate_workflow_statuses(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    return await run_fix_duplicate_workflow_statuses(user)


@router.get("/s3/cors-status")
@router.post("/s3/fix-cors")
async def s3_cors_diagnostic(force_fix: bool = False, request: Request = None, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_s3_cors_diagnostic(force_fix, request, user)


@router.post("/workflow-statuses/migrate-portal-labels")
async def migrate_portal_labels(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_migrate_portal_labels(user)


@router.post("/processes/fix-duplicates")
async def fix_duplicate_processes(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    return await run_fix_duplicate_processes(user)


@router.get("/users", response_model=List[UserResponse])
async def get_users(
    role: Optional[str] = None,
    for_assignment: bool = Query(
        False,
        description="Se true, devolve só staff elegível para atribuições "
        "(exclui admin e indexação).",
    ),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO])),
):
    return await run_get_users(user, role, for_assignment=for_assignment)


@router.post("/users", response_model=UserResponse)
async def create_user(data: UserCreate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_create_user(data, user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, data: UserUpdate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_update_user(user_id, data, user)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_delete_user(user_id, user)


@router.get("/users/{user_id}/roles")
async def list_user_roles(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Lista os acessos UCR (empresa + cargo) de um utilizador."""
    return await run_list_user_company_roles(user_id=user_id)


@router.post("/users/{user_id}/roles")
async def assign_user_role(
    user_id: str,
    payload: UserRoleAssignBody,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Adiciona um acesso (empresa + cargo) a um utilizador."""
    return await run_assign_user_company_role(user_id, payload)


@router.delete("/users/{user_id}/roles/{role_id}")
async def delete_user_role(
    user_id: str,
    role_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """Remove um acesso UCR (empresa + cargo) de um utilizador."""
    return await run_delete_user_company_role(role_id, user_id=user_id)


@router.post("/impersonate/{user_id}")
async def impersonate_user(user_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_impersonate_user(user_id, user)


@router.post("/stop-impersonate")
async def stop_impersonate(user: dict = Depends(get_current_user)):
    return await run_stop_impersonate(user)


@router.post("/migrate-process-numbers")
async def migrate_process_numbers(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    return await run_migrate_process_numbers(user)


@router.post("/update-process-active-status")
async def update_process_active_status(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    return await run_update_process_active_status(user)


@router.get("/ai-training")
async def get_ai_training_data(
    category: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_training_data(category, user)


@router.post("/ai-training")
async def add_ai_training_entry(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_add_ai_training_entry(data, user)


@router.put("/ai-training/{entry_id}")
async def update_ai_training_entry(
    entry_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_update_ai_training_entry(entry_id, data, user)


@router.delete("/ai-training/{entry_id}")
async def delete_ai_training_entry(
    entry_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_delete_ai_training_entry(entry_id, user)


@router.get("/ai-training/prompt")
async def get_ai_training_prompt(
    category: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_training_prompt(category, user)


@router.post("/ai-training/prompt/execute")
async def record_ai_prompt_execution(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_record_ai_prompt_execution(user)


@router.get("/ai-training/stats")
async def get_ai_training_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_training_stats(user)


@router.get("/notification-preferences/{user_id}")
async def get_notification_preferences(
    user_id: str,
    company_id: Optional[str] = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    # PACOTE DF — `company_id` query param opcional permite ler preferências
    # por-UCR (user_company_roles.notification_preferences).
    return await run_get_notification_preferences(user_id, user, company_id=company_id)


@router.put("/notification-preferences/{user_id}")
async def update_notification_preferences(
    user_id: str,
    preferences: dict,
    company_id: Optional[str] = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    # PACOTE DF — `company_id` query param opcional permite gravar preferências
    # por-UCR (user_company_roles.notification_preferences) com fallback global.
    return await run_update_notification_preferences(user_id, preferences, user, company_id=company_id)


@router.get("/notification-preferences")
async def get_all_notification_preferences(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_all_notification_preferences(user)


@router.post("/notification-preferences/bulk-update")
async def bulk_update_notification_preferences(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_bulk_update_notification_preferences(data, user)


@router.get("/system-logs")
async def get_system_error_logs(
    page: int = 1,
    limit: int = 50,
    severity: str = None,
    component: str = None,
    error_type: str = None,
    resolved: bool = None,
    days: int = 7,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_system_error_logs(
        user, page, limit, severity, component, error_type, resolved, days
    )


@router.get("/system-logs/stats")
async def get_system_logs_stats(
    days: int = 7,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_system_logs_stats(user, days)


@router.get("/system-logs/{error_id}")
async def get_system_log_detail(
    error_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_system_log_detail(error_id, user)


@router.post("/system-logs/mark-read")
async def mark_errors_as_read(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_mark_errors_as_read(data, user)


@router.post("/system-logs/{error_id}/resolve")
async def resolve_system_error(
    error_id: str,
    data: dict = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_resolve_system_error(error_id, user, data)


@router.post("/system-logs/bulk-resolve")
async def bulk_resolve_system_errors(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_bulk_resolve_system_errors(data, user)


@router.post("/system-logs/resolve-all")
async def resolve_all_system_errors(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_resolve_all_system_errors(user)


@router.delete("/system-logs/cleanup")
async def cleanup_old_system_logs(
    days: int = 90,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_cleanup_old_system_logs(user, days)


@router.get("/db/indexes")
async def get_database_indexes(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_database_indexes(user)


@router.get("/ai-import-logs")
async def get_ai_import_logs(
    page: int = 1,
    limit: int = 50,
    status: str = None,
    days: int = 7,
    client_name: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_import_logs(user, page, limit, status, days, client_name)


@router.post("/ai-import-logs/{log_id}/resolve")
async def resolve_ai_import_log(
    log_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_resolve_ai_import_log(log_id, user)


@router.post("/ai-import-logs/bulk-resolve")
async def bulk_resolve_ai_import_logs(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_bulk_resolve_ai_import_logs(data, user)


@router.get("/ai-import-logs-v2/grouped")
async def get_ai_import_logs_grouped(
    days: int = 7,
    status: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_import_logs_grouped(user, days, status)


@router.get("/ai-import-logs-v2")
async def get_ai_import_logs_v2(
    page: int = 1,
    limit: int = 50,
    status: str = None,
    days: int = 7,
    client_name: str = None,
    document_type: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_import_logs_v2(
        user, page, limit, status, days, client_name, document_type
    )


@router.get("/ai-import-logs-v2/{log_id}")
async def get_ai_import_log_detail(
    log_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_ai_import_log_detail(log_id, user)


@router.post("/db/indexes/repair")
async def repair_database_indexes(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_repair_database_indexes(user)


@router.delete("/db/indexes/{collection}/{index_name}")
async def drop_specific_index(
    collection: str,
    index_name: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_drop_specific_index(collection, index_name, user)


@router.delete("/cleanup/jobs")
async def cleanup_old_jobs(
    days: int = Query(default=7, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_cleanup_old_jobs(days, user)


@router.delete("/cleanup/error-logs")
async def cleanup_old_error_logs(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_cleanup_old_error_logs(days, user)


@router.get("/jobs/health")
async def get_jobs_health(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_jobs_health(user)


@router.post("/jobs/cancel/{job_id}")
async def cancel_stuck_job(
    job_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_cancel_stuck_job(job_id, user)


@router.get("/client-registrations")
async def list_client_registrations(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    source: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_list_client_registrations(user, page, limit, search, status, source)


@router.get("/client-registrations/{process_id}")
async def get_client_registration(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_client_registration(process_id, user)


@router.put("/client-registrations/{process_id}")
async def update_client_registration(
    process_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_update_client_registration(process_id, data, user)


@router.delete("/client-registrations/{process_id}")
async def delete_client_registration(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_delete_client_registration(process_id, user)


@router.get("/client-registrations/stats/summary")
async def get_client_registrations_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_client_registrations_stats(user)


@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(100, le=500),
    skip: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    entity: Optional[str] = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_audit_logs(user, limit, skip, action, entity)


@router.get("/stale-processes")
async def get_stale_processes(
    days: int = Query(14, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    return await run_get_stale_processes(user, days)


@router.get("/team-performance")
async def get_team_performance(
    start_date: Optional[str] = Query(None, description="Data de início (YYYY-MM-DD). Por defeito, há 7 dias"),
    end_date: Optional[str] = Query(None, description="Data de fim (YYYY-MM-DD). Por defeito, hoje"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_get_team_performance(user, start_date, end_date)


@router.get("/sync-database/status")
async def get_sync_status(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_sync_status(user)


@router.post("/sync-database")
async def sync_database(
    request: SyncDatabaseRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_sync_database(request, background_tasks, user)


@router.get("/users/{user_id}/email-config")
async def admin_get_user_email_config(
    user_id: str,
    admin: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_admin_get_user_email_config(user_id, admin)


@router.post("/users/{user_id}/email-config")
async def admin_set_user_email_config(
    user_id: str,
    config: "EmailConfigCreate",
    admin: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_admin_set_user_email_config(user_id, config, admin)


@router.post("/users/{user_id}/email-config/test")
async def admin_test_user_email_config(
    user_id: str,
    admin: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    return await run_admin_test_user_email_config(user_id, admin)


@router.post("/sync-process-emails")
async def sync_process_emails(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    return await run_sync_process_emails(user)


@router.post("/seed-realistic-data")
async def seed_realistic_data_endpoint(
    request: Request,
    body: SeedRequest = None,
    current_user: dict = Depends(require_roles("admin")),
):
    return await run_seed_realistic_data(request, body, current_user)


