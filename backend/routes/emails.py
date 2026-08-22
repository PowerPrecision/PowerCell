"""
====================================================================
ROTAS DE EMAILS - POWERCELL
====================================================================
Thin FastAPI stubs — logic lives in services/email_*.py
====================================================================
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks, UploadFile, File, Request

from models.email import (
    EmailCreate, EmailUpdate, EmailResponse, EmailDirection,
    EmailMarkType, EmailTemplateCreate, EmailTemplateResponse, EmailFilter, EmailSendRequest,
    LabelCreateRequest, LabelUpdateRequest,
    FolderCreateRequest, FolderUpdateRequest
)
from services.auth import get_current_user

from services.email_labels_folders import (
    run_list_labels,
    run_create_label,
    run_update_label,
    run_delete_label,
    run_list_folders,
    run_create_folder,
    run_update_folder,
    run_delete_folder,
    run_move_emails_to_folder,
)
from services.email_documentation import (
    run_get_document_recipients,
    run_preview_email_template,
    run_preview_documentation_email,
    run_send_documentation_email,
)
from services.email_mailbox_ops import (
    run_upload_attachments,
    run_download_email_attachment,
    run_mark_email,
    run_unmark_email,
    run_add_email_label,
    run_remove_email_label,
    run_get_email_attachments,
    run_download_attachment,
    run_preview_attachment,
)
from services.email_templates_drafts import (
    run_get_email_templates,
    run_create_email_template,
    run_update_email_template,
    run_delete_email_template,
    run_use_template,
    run_get_unread_notifications,
    run_list_auto_drafts,
    run_auto_drafts_stats,
    run_edit_auto_draft,
    run_send_auto_draft,
    run_delete_auto_draft,
    run_manually_create_draft,
)
from services.email_webmail import (
    run_test_email_connections,
    run_get_configured_accounts,
    run_webmail_list,
    run_webmail_stats,
    run_webmail_sync,
    run_webmail_sync_user,
    run_get_email_job_status,
)
from services.email_process_crud import (
    run_advanced_email_search,
    run_get_email_timeline,
    run_get_process_emails,
    run_get_email_stats,
    run_sync_process_emails,
    run_get_sync_status,
    run_associate_email_to_client,
    run_search_emails,
    run_send_email,
    run_create_email_record,
    run_get_email,
    run_update_email,
    run_delete_email,
    run_permanently_delete_email,
    run_get_monitored_emails,
    run_add_monitored_email,
    run_remove_monitored_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

# NOTA: doc_router foi removido. Endpoints send-documentation / document-recipients
# estão no router principal ANTES das rotas com /{email_id}.
doc_router = None  # compat server.py

# ==== DOCUMENT RECIPIENTS & SEND DOCUMENTATION (antes de /{email_id} para evitar conflito) ====

@router.get("/document-recipients")
async def get_document_recipients(
    current_user: dict = Depends(get_current_user)
):
    """Obter lista de destinatários disponíveis para envio de documentação."""
    return await run_get_document_recipients(current_user)


@router.post("/preview-template")
async def preview_email_template(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Pré-visualiza o template de email de documentação com dados de exemplo."""
    return await run_preview_email_template(data, current_user)


@router.get("/preview-documentation/{process_id}")
async def preview_documentation_email(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Gera e devolve o HTML final do email de documentação sem o enviar."""
    return await run_preview_documentation_email(process_id, current_user)


@router.post("/send-documentation/{process_id}")
async def send_documentation_email(
    process_id: str,
    request: Request,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Envia documentação do processo para balcões/bancos com anexos do S3."""
    return await run_send_documentation_email(process_id, data, current_user, request)


# ==== LABELS CRUD (user-level labels) ====

@router.get("/labels")
async def list_labels(
    current_user: dict = Depends(get_current_user)
):
    """Listar todas as labels do utilizador. Cria labels predefinidas na primeira chamada."""
    return await run_list_labels(current_user)


@router.post("/labels")
async def create_label(
    payload: LabelCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Criar uma nova label."""
    return await run_create_label(payload, current_user)


@router.put("/labels/{label_id}")
async def update_label(
    label_id: str,
    payload: LabelUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar nome e/ou cor de uma label."""
    return await run_update_label(label_id, payload, current_user)


@router.delete("/labels/{label_id}")
async def delete_label(
    label_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar label e remover de todos os emails do utilizador."""
    return await run_delete_label(label_id, current_user)


# ==== FOLDERS CRUD (user-level custom folders) ====

@router.get("/folders")
async def list_folders(
    current_user: dict = Depends(get_current_user)
):
    """Listar todas as pastas personalizadas do utilizador."""
    return await run_list_folders(current_user)


@router.post("/folders")
async def create_folder(
    payload: FolderCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Criar uma nova pasta personalizada."""
    return await run_create_folder(payload, current_user)


@router.put("/folders/{folder_id}")
async def update_folder(
    folder_id: str,
    payload: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar nome e/ou cor de uma pasta."""
    return await run_update_folder(folder_id, payload, current_user)


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar pasta e remover referência dos emails (emails voltam à pasta de origem)."""
    return await run_delete_folder(folder_id, current_user)


@router.post("/emails/move-to-folder")
async def move_emails_to_folder(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Mover um ou mais emails para uma pasta personalizada."""
    return await run_move_emails_to_folder(data, current_user)


# ==== ATTACHMENT UPLOAD ====

@router.post("/attachments/upload")
async def upload_attachments(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Carregar um ou mais ficheiros para o S3 (pasta temporária)."""
    return await run_upload_attachments(files, current_user)


@router.get("/{email_id}/attachments/{file_id}/download")
async def download_email_attachment(
    email_id: str,
    file_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter URL pré-assinada para download de anexo de email."""
    return await run_download_email_attachment(email_id, file_id, current_user)


@router.post("/{email_id}/mark")
async def mark_email(
    email_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Marcar um email como importante, lido, etc."""
    return await run_mark_email(email_id, data, current_user)


@router.delete("/{email_id}/mark/{mark_type}")
async def unmark_email(
    email_id: str,
    mark_type: EmailMarkType,
    current_user: dict = Depends(get_current_user)
):
    """Remover marcação de email."""
    return await run_unmark_email(email_id, mark_type, current_user)


@router.post("/{email_id}/labels")
async def add_email_label(
    email_id: str,
    label: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Adicionar etiqueta ao email."""
    return await run_add_email_label(email_id, label, current_user)


@router.delete("/{email_id}/labels/{label}")
async def remove_email_label(
    email_id: str,
    label: str,
    current_user: dict = Depends(get_current_user)
):
    """Remover etiqueta do email."""
    return await run_remove_email_label(email_id, label, current_user)


@router.get("/{email_id}/attachments")
async def get_email_attachments(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Listar anexos de um email."""
    return await run_get_email_attachments(email_id, current_user)


@router.get("/{email_id}/attachments/{attachment_id}")
async def download_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download de anexo."""
    return await run_download_attachment(email_id, attachment_id, current_user)


@router.get("/{email_id}/attachments/{attachment_id}/preview")
async def preview_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Preview de anexo (para imagens e PDFs)."""
    return await run_preview_attachment(email_id, attachment_id, current_user)



# ==== FILTROS AVANÇADOS ====

@router.post("/search/advanced")
async def advanced_email_search(
    filters: EmailFilter,
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    return await run_advanced_email_search(filters, current_user, page=page, limit=limit)


@router.get("/timeline/{process_id}")
async def get_email_timeline(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_email_timeline(process_id, current_user)


# ==== TEMPLATES DE RESPOSTA ====

@router.get("/templates", response_model=List[EmailTemplateResponse])
async def get_email_templates(
    request: Request,
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_email_templates(request, current_user, category=category)


@router.post("/templates", response_model=EmailTemplateResponse)
async def create_email_template(
    template: EmailTemplateCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    return await run_create_email_template(template, request, current_user)


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    return await run_update_email_template(template_id, template, current_user)


@router.delete("/templates/{template_id}")
async def delete_email_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_delete_email_template(template_id, current_user)


@router.post("/templates/{template_id}/use")
async def use_template(
    template_id: str,
    process_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    return await run_use_template(template_id, process_id, current_user)


# ==== NOTIFICAÇÕES ====

@router.get("/notifications/unread")
async def get_unread_notifications(
    current_user: dict = Depends(get_current_user)
):
    return await run_get_unread_notifications(current_user)


@router.get("/test-connection")
async def test_email_connections(
    account: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return await run_test_email_connections(current_user, account=account)


@router.get("/accounts")
async def get_configured_accounts(
    current_user: dict = Depends(get_current_user)
):
    return await run_get_configured_accounts(current_user)


# ==== WEBMAIL ====

@router.get("/webmail")
async def webmail_list(
    request: Request,
    folder: str = Query("inbox"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, le=100),
    account: Optional[str] = None,
    search: Optional[str] = None,
    label: Optional[str] = None,
    custom_folder: Optional[str] = None,
    box: Optional[str] = None,
    mailbox: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return await run_webmail_list(
        request, current_user,
        folder=folder, page=page, limit=limit, account=account,
        search=search, label=label, custom_folder=custom_folder, box=box,
        mailbox=mailbox,
    )


@router.get("/webmail-stats")
async def webmail_stats(
    request: Request,
    box: Optional[str] = None,
    mailbox: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return await run_webmail_stats(
        current_user, box=box, request=request, mailbox=mailbox,
    )


@router.post("/webmail/sync")
async def webmail_sync(
    request: Request,
    account: Optional[str] = None,
    days: int = Query(7, ge=1, le=30),
    current_user: dict = Depends(get_current_user)
):
    return await run_webmail_sync(
        current_user, account=account, days=days, request=request,
    )


@router.post("/webmail/sync-user")
async def webmail_sync_user(
    request: Request,
    account_id: Optional[str] = None,
    mailbox: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    return await run_webmail_sync_user(
        request, current_user, account_id=account_id, mailbox=mailbox,
    )


@router.get("/jobs/{job_id}")
async def get_email_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_email_job_status(job_id, current_user)


@router.get("/process/{process_id}", response_model=List[EmailResponse])
async def get_process_emails(
    process_id: str,
    direction: Optional[EmailDirection] = None,
    filter_by_user: bool = False,
    include_archived: bool = False,
    force_refresh: bool = False,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_process_emails(
        process_id, current_user,
        direction=direction, filter_by_user=filter_by_user,
        include_archived=include_archived, force_refresh=force_refresh,
    )


@router.get("/stats/{process_id}")
async def get_email_stats(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_email_stats(process_id, current_user)


@router.post("/sync/{process_id}")
async def sync_process_emails(
    process_id: str,
    background_tasks: BackgroundTasks,
    days: int = Query(30, ge=1, le=365),
    blocking: bool = False,
    current_user: dict = Depends(get_current_user)
):
    return await run_sync_process_emails(
        process_id, background_tasks, current_user, days=days, blocking=blocking,
    )


@router.get("/sync-status/{process_id}")
async def get_sync_status(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_sync_status(process_id, current_user)


@router.post("/associate")
async def associate_email_to_client(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    return await run_associate_email_to_client(data, current_user)


@router.get("/search")
async def search_emails(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    return await run_search_emails(q, current_user, limit=limit)


@router.post("/send")
async def send_email_endpoint(
    payload: EmailSendRequest,
    request: Request,
    account: str = Query("power"),
    current_user: dict = Depends(get_current_user)
):
    return await run_send_email(payload, request, current_user, account=account)


# ==== RASCUNHOS AUTOMÁTICOS (Auto-Draft) ====

@router.get("/drafts")
async def list_auto_drafts(
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    return await run_list_auto_drafts(current_user, limit=limit)


@router.get("/drafts/stats")
async def auto_drafts_stats(
    current_user: dict = Depends(get_current_user)
):
    return await run_auto_drafts_stats(current_user)


@router.put("/drafts/{draft_id}")
async def edit_auto_draft(
    draft_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    return await run_edit_auto_draft(draft_id, data, current_user)


@router.post("/drafts/{draft_id}/send")
async def send_auto_draft(
    draft_id: str,
    account: str = Query("power", description="Conta de email (power/precision)"),
    current_user: dict = Depends(get_current_user)
):
    return await run_send_auto_draft(draft_id, current_user, account=account)


@router.delete("/drafts/{draft_id}")
async def delete_auto_draft(
    draft_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_delete_auto_draft(draft_id, current_user)


@router.post("/drafts/create")
async def manually_create_draft(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    return await run_manually_create_draft(data, current_user)


# ==== ROTAS CRUD GENÉRICAS ====

@router.post("", response_model=EmailResponse)
async def create_email_record(
    email_data: EmailCreate,
    current_user: dict = Depends(get_current_user)
):
    return await run_create_email_record(email_data, current_user)


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_email(email_id, request, current_user)


@router.put("/{email_id}", response_model=EmailResponse)
async def update_email(
    email_id: str,
    email_data: EmailUpdate,
    current_user: dict = Depends(get_current_user)
):
    return await run_update_email(email_id, email_data, current_user)


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_delete_email(email_id, current_user)


@router.delete("/{email_id}/permanent")
async def permanently_delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_permanently_delete_email(email_id, current_user)


# ==== GESTÃO DE EMAILS MONITORIZADOS ====

@router.get("/monitored/{process_id}")
async def get_monitored_emails(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_get_monitored_emails(process_id, current_user)


@router.post("/monitored/{process_id}")
async def add_monitored_email(
    process_id: str,
    email: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    return await run_add_monitored_email(process_id, email, current_user)


@router.delete("/monitored/{process_id}/{email}")
async def remove_monitored_email(
    process_id: str,
    email: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_remove_monitored_email(process_id, email, current_user)

