"""
====================================================================
ROTAS DE EMAILS - POWERCELL
====================================================================
Endpoints para gestão de histórico de emails.

FEATURES:
- Visualização de anexos (preview, download)
- Filtros avançados (por data, por conta, por tipo)
- Marcação de emails (importante, lido, etc.)
- Templates de resposta rápida
- Timeline de emails no processo
- Notificações de novos emails
====================================================================
"""

import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import base64

from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks, UploadFile, File, Form, Request
from fastapi.responses import Response
import re

from database import db
from models.email import (
    EmailCreate, EmailUpdate, EmailResponse, EmailDirection, EmailStatus,
    EmailMarkType, EmailTemplateCreate, EmailTemplateResponse, EmailFilter, EmailSendRequest,
    LabelCreateRequest, LabelUpdateRequest,
    FolderCreateRequest, FolderUpdateRequest
)
from services.auth import get_current_user, get_effective_role
from services.email_service import sync_emails_for_process, send_email, test_email_connection, get_email_accounts, get_email_accounts_async, sync_webmail_emails, imap_mark_as_seen, imap_mark_as_unseen, imap_delete_message, imap_move_to_trash, _get_email_account_for_email
from services.email_draft_service import (
    get_pending_drafts,
    get_draft_stats,
    update_draft,
    send_draft,
    discard_draft,
    create_missing_doc_draft,
    batch_create_missing_doc_drafts,
)
from services.email_enrich import enrich_email
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
from utils.input_sanitization import sanitize_string, sanitize_name, sanitize_email, sanitize_html, sanitize_url, log_sanitization_rejection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

# NOTA: doc_router foi removido. Os endpoints send-documentation e document-recipients
# estão agora registados no router principal ANTES das rotas com /{email_id}.
# Isto resolve o bug 404 que ocorria quando a ordem de montagem dos routers
# no server.py causava conflitos com o catch-all /{email_id}.
doc_router = None  # Mantido como None para compatibilidade com server.py

# Armazenar status de sincronizações em progresso
_sync_status = {}



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
    """
    Pesquisa avançada de emails com filtros.
    
    Suporta:
    - Filtro por processo
    - Filtro por direção (enviado/recebido)
    - Filtro por conta (precision/power)
    - Filtro por marcações (importante, lido, estrela)
    - Filtro por anexos
    - Filtro por intervalo de datas
    - Pesquisa por texto
    - Filtro por etiquetas
    """
    query = {}
    
    # Filtro por processo
    if filters.process_id:
        query["process_id"] = filters.process_id
    
    # Filtro por direcção
    if filters.direction:
        query["direction"] = filters.direction.value
    
    # Filtro por conta
    if filters.account:
        query["account"] = filters.account
    
    # Filtros de marcação
    if filters.is_important is not None:
        query["is_important"] = filters.is_important
    if filters.is_read is not None:
        query["is_read"] = filters.is_read
    if filters.is_starred is not None:
        query["is_starred"] = filters.is_starred
    if filters.is_archived is not None:
        query["is_archived"] = filters.is_archived
    
    # Filtro por anexos
    if filters.has_attachments is not None:
        if filters.has_attachments:
            query["attachments.0"] = {"$exists": True}
        else:
            query["attachments"] = {"$size": 0}
    
    # Filtro por datas
    if filters.date_from or filters.date_to:
        date_query = {}
        if filters.date_from:
            date_query["$gte"] = filters.date_from
        if filters.date_to:
            date_query["$lte"] = filters.date_to
        query["sent_at"] = date_query
    
    # Pesquisa por texto
    if filters.search_term:
        query["$or"] = [
            {"subject": {"$regex": filters.search_term, "$options": "i"}},
            {"body": {"$regex": filters.search_term, "$options": "i"}},
            {"from_email": {"$regex": filters.search_term, "$options": "i"}},
            {"to_emails": {"$regex": filters.search_term, "$options": "i"}},
        ]
    
    # Filtro por etiquetas
    if filters.labels:
        query["labels"] = {"$all": filters.labels}
    
    # Executar query com paginação
    skip = (page - 1) * limit
    total = await db.emails.count_documents(query)
    
    emails = await db.emails.find(
        query,
        {"_id": 0}
    ).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Enriquecer emails
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(enriched)
    
    return {
        "emails": enriched_emails,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


# ==== TIMELINE DE EMAILS ====

@router.get("/timeline/{process_id}")
async def get_email_timeline(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obter timeline de emails de um processo.
    Inclui eventos agrupados por dia.
    """
    emails = await db.emails.find(
        {"process_id": process_id, "is_archived": {"$ne": True}},
        {"_id": 0}
    ).sort("sent_at", 1).to_list(500)
    
    # Agrupar por data
    timeline = {}
    for email in emails:
        if email.get("sent_at"):
            date_key = email["sent_at"][:10]  # YYYY-MM-DD
            if date_key not in timeline:
                timeline[date_key] = {
                    "date": date_key,
                    "emails": [],
                    "stats": {"sent": 0, "received": 0}
                }
            
            timeline[date_key]["emails"].append(email)
            if email.get("direction") == "sent":
                timeline[date_key]["stats"]["sent"] += 1
            else:
                timeline[date_key]["stats"]["received"] += 1
    
    # Converter para lista ordenada
    timeline_list = sorted(timeline.values(), key=lambda x: x["date"], reverse=True)
    
    return {"timeline": timeline_list, "total_emails": len(emails)}


# ==== TEMPLATES DE RESPOSTA ====

@router.get("/templates", response_model=List[EmailTemplateResponse])
async def get_email_templates(
    request: Request,
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Listar templates de resposta rápida filtrados pela empresa ativa."""
    from services.auth import get_active_company_id_async

    query = {}
    if category:
        query["category"] = category

    # MULTI-EMPRESA: filtrar templates por empresa ativa
    # Mostrar: templates da empresa ativa + templates globais (sem company_id)
    try:
        active_company_id = await get_active_company_id_async(request, current_user)
        if active_company_id:
            query["$or"] = [
                {"company_id": active_company_id},
                {"company_id": {"$exists": False}},
                {"company_id": None},
                {"company_id": ""},
            ]
    except Exception:
        pass  # Fallback: mostrar todos se não houver contexto

    templates = await db.email_templates.find(
        query,
        {"_id": 0}
    ).sort("usage_count", -1).to_list(50)

    return templates


@router.post("/templates", response_model=EmailTemplateResponse)
async def create_email_template(
    template: EmailTemplateCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Criar novo template de resposta."""
    from services.auth import get_active_company_id_async

    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # MULTI-EMPRESA: determinar company_id para este template
    company_id = "default"
    try:
        active_company_id = await get_active_company_id_async(request, current_user)
        if active_company_id:
            company_id = active_company_id
    except Exception:
        pass

    template_doc = {
        "id": template_id,
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_string(template.subject, max_length=300),
        "body": sanitize_string(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "company_id": company_id,  # MULTI-EMPRESA
        "created_by": current_user["id"],
        "created_at": now,
        "usage_count": 0
    }
    
    # Se for default, remover default de outros
    if template.is_default:
        await db.email_templates.update_many(
            {"category": template.category},
            {"$set": {"is_default": False}}
        )
    
    await db.email_templates.insert_one(template_doc)
    
    return EmailTemplateResponse(**template_doc)


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Actualizar template de resposta."""
    existing = await db.email_templates.find_one({"id": template_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    update_data = {
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_string(template.subject, max_length=300),
        "body": sanitize_string(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.email_templates.update_one(
        {"id": template_id},
        {"$set": update_data}
    )
    
    updated = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    return EmailTemplateResponse(**updated)


@router.delete("/templates/{template_id}")
async def delete_email_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar template de resposta."""
    result = await db.email_templates.delete_one({"id": template_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"success": True}


@router.post("/templates/{template_id}/use")
async def use_template(
    template_id: str,
    process_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Incrementar contador de uso de template."""
    await db.email_templates.update_one(
        {"id": template_id},
        {"$inc": {"usage_count": 1}}
    )
    
    # Obter template
    template = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    
    # Obter dados do processo para personalizar
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    # Substituir variáveis
    body = template.get("body", "")
    subject = template.get("subject", "")
    
    if process:
        body = body.replace("{cliente}", process.get("client_name", ""))
        body = body.replace("{email_cliente}", process.get("client_email", ""))
        subject = subject.replace("{cliente}", process.get("client_name", ""))
    
    return {
        "subject": subject,
        "body": body
    }


# ==== NOTIFICAÇÕES ====

@router.get("/notifications/unread")
async def get_unread_notifications(
    current_user: dict = Depends(get_current_user)
):
    """
    Obter contagem de emails não lidos por processo.
    Para mostrar badges de notificação.
    """
    # Obter processos do utilizador
    user_email = current_user.get("email", "").lower()
    
    # Admin/CEO veem todos, outros só os seus
    if current_user["role"] in ["admin", "ceo"]:
        processes = await db.processes.find({}, {"_id": 0, "id": 1, "client_name": 1}).to_list(1000)
    else:
        processes = await db.processes.find(
            {"assigned_to": current_user["id"]},
            {"_id": 0, "id": 1, "client_name": 1}
        ).to_list(1000)
    
    process_ids = [p["id"] for p in processes]
    
    # Contar emails não lidos por processo
    pipeline = [
        {"$match": {
            "process_id": {"$in": process_ids},
            "is_read": False,
            "is_archived": {"$ne": True}
        }},
        {"$group": {
            "_id": "$process_id",
            "count": {"$sum": 1},
            "latest": {"$max": "$sent_at"}
        }}
    ]
    
    unread_counts = await db.emails.aggregate(pipeline).to_list(1000)
    
    # Mapear para resposta
    result = {}
    for item in unread_counts:
        process_id = item["_id"]
        process = next((p for p in processes if p["id"] == process_id), None)
        if process:
            result[process_id] = {
                "count": item["count"],
                "latest": item["latest"],
                "client_name": process.get("client_name", "")
            }
    
    total_unread = sum(r["count"] for r in result.values())
    
    return {
        "total_unread": total_unread,
        "by_process": result
    }


@router.get("/test-connection")
async def test_email_connections(
    account: Optional[str] = Query(None, description="Conta específica (precision, power) ou todas"),
    current_user: dict = Depends(get_current_user)
):
    """Testar ligação com as contas de email."""
    if current_user["role"] not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    results = await test_email_connection(account)
    return results


@router.get("/accounts")
async def get_configured_accounts(
    current_user: dict = Depends(get_current_user)
):
    """Listar contas de email configuradas."""
    accounts = get_email_accounts()
    return [
        {
            "name": a.name,
            "email": a.email,
            "imap_server": a.imap_server,
            "smtp_server": a.smtp_server
        }
        for a in accounts
    ]


# ==== WEBMAIL - LISTAGEM POR PASTA ====

@router.get("/webmail")
async def webmail_list(
    request: Request,
    folder: str = Query("inbox", description="Pasta: inbox, sent, drafts, starred, trash, custom"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, le=100),
    account: Optional[str] = Query(None, description="Conta IMAP: power, precision"),
    search: Optional[str] = Query(None, description="Pesquisa texto"),
    label: Optional[str] = Query(None, description="Filtrar por label"),
    custom_folder: Optional[str] = Query(None, description="ID de pasta personalizada"),
    box: Optional[str] = Query(None, description="Caixa: personal, general, shared_indexacao"),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar emails no formato Webmail por pasta.
    
    ISOLAMENTO DE DADOS (Segurança):
    - admin/ceo/diretor: podem ver TODOS os emails (caixa geral)
    - outros roles (consultor, intermediario, etc.): só vêem emails onde são
      recipient (inbox) ou sender (sent). Filtragem por endereço de email.
    
    BOX PARAM (Tabbed webmail):
    - personal: emails do utilizador (synced_for_user ou created_by)
    - general: emails partilhados da caixa geral (shared_role=geral)
    - shared_indexacao: emails partilhados do role indexacao
    
    - inbox: emails recebidos (direction=received, não arquivados)
    - sent: emails enviados (direction=sent)
    - starred: emails marcados como estrela
    - trash: emails arquivados
    - drafts: emails com status=draft
    - custom: emails numa pasta personalizada (requer custom_folder param)
    """
    from models.auth import UserRole
    
    user_email = (current_user.get("email") or "").lower().strip()
    user_role = current_user.get("role", "")  # Used for permission checks (403)
    user_id = current_user.get("id", "")
    effective_role = get_effective_role(request, current_user)  # Used for data filtering
    can_see_all = effective_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    
    logger.debug(f"User {current_user.get('email')} (id={user_id}, role={user_role}, effective_role={effective_role}) querying box={box} folder={folder} account={account}")
    
    # === BOX FILTER: permissões e isolamento por caixa ===
    if box == "general":
        # Blocked for consultor and indexacao
        if user_role in (UserRole.CONSULTOR, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'geral' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail List] box=general, user={user_email}, role={user_role}")
    elif box == "shared_indexacao":
        # Blocked for everyone except admin and indexacao
        if user_role not in (UserRole.ADMIN, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'shared_indexacao' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail List] box=shared_indexacao, user={user_email}, role={user_role}")
    elif box == "personal":
        logger.info(f"[Webmail List] box=personal, user={user_email}, role={user_role}")
    
    # === OBTER EMAIL DA CONTA IMAP SELECIONADA ===
    # Quando o user seleciona uma conta (ex: "power"), obtém o email dessa conta
    # para incluir no filtro — permite ver emails da caixa partilhada.
    account_email = None
    if account:
        try:
            accounts = await get_email_accounts_async()
            for acc in accounts:
                if acc.name == account:
                    account_email = (acc.email or "").lower().strip()
                    break
        except Exception:
            pass
    
    # === CONSTRUIR QUERY USANDO $and PARA EVITAR CONFLITOS ENTRE $or ===
    # Cada condição independente entra como um elemento separado do $and.
    # Isso evita que múltiplos $or se sobreponham.
    and_conditions = []
    
    # === MULTI-EMPRESA: filtrar emails por empresa ativa ===
    # Mostrar: emails da empresa ativa + emails globais (sem company_id)
    try:
        from services.auth import get_active_company_id_async
        active_company_id = await get_active_company_id_async(request, current_user)
        if active_company_id:
            and_conditions.append({"$or": [
                {"company_id": active_company_id},
                {"company_id": {"$exists": False}},
                {"company_id": None},
                {"company_id": ""},
            ]})
    except Exception:
        pass  # Fallback: mostrar todos se não houver contexto
    
    # === ISOLAMENTO POR UTILIZADOR ===
    # Quando box é fornecido, ele substitui a lógica de isolamento padrão.
    # Quando box não é fornecido, mantém o comportamento actual.
    if box:
        # --- BOX-SPECIFIC ISOLATION ---
        if box == "personal":
            # Emails onde synced_for_user ou created_by corresponde ao utilizador
            # synced_for_user pode ser gravado como user_id OU como user.email,
            # por isso procuramos por ambos.
            ownership_filter = {
                "$or": [
                    {"created_by": user_id},
                    {"synced_for_user": user_id},
                    {"synced_for_user": user_email},
                ]
            }
            if folder == "inbox":
                # Quando box=personal, synced_for_user é o carimbo de propriedade.
                # Se synced_for_user corresponde ao user, NÃO filtramos adicionalmente
                # por to_emails — o email pode vir de uma conta IMAP com endereço diferente
                # do login do utilizador (ex: conta partilhada da empresa).
                # Apenas filter por to_emails quando o email NÃO tem synced_for_user.
                ownership_only = {
                    "$or": [
                        {"synced_for_user": user_id},
                        {"synced_for_user": user_email},
                    ]
                }
                ownership_with_to = {
                    "$and": [
                        {"$or": [
                            {"created_by": user_id},
                        ]},
                        {"$or": [
                            {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                        ]},
                    ]
                }
                if account_email and account_email != user_email:
                    ownership_with_to["$and"][1]["$or"].append(
                        {"to_emails": {"$regex": re.escape(account_email), "$options": "i"}}
                    )
                and_conditions.append({
                    "$or": [ownership_only, ownership_with_to]
                })
            elif folder == "sent":
                # Sent emails: synced_for_user match, OR created_by match, OR from_email match
                ownership_only = {
                    "$or": [
                        {"synced_for_user": user_id},
                        {"synced_for_user": user_email},
                        {"created_by": user_id},
                    ]
                }
                ownership_with_from = {
                    "$or": [
                        {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                    ]
                }
                if account_email and account_email != user_email:
                    ownership_with_from["$or"].append(
                        {"from_email": {"$regex": re.escape(account_email), "$options": "i"}}
                    )
                and_conditions.append({
                    "$or": [ownership_only, ownership_with_from]
                })
            elif folder == "drafts":
                and_conditions.append({"created_by": user_id})
            elif folder in ("starred", "trash", "custom"):
                # For starred/trash/custom: show emails owned by user OR where user's email appears
                shared_or = [
                    {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                    {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                    {"created_by": user_id},
                ]
                if account_email and account_email != user_email:
                    shared_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
                    shared_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
                and_conditions.append({
                    "$or": [ownership_filter, {"$or": shared_or}]
                })
        elif box == "general":
            # Emails com shared_role=geral (caixa geral) OU is_general=True
            # (sync global via IMAP que marca is_general=True)
            and_conditions.append({"$or": [{"shared_role": "geral"}, {"is_general": True}]})
        elif box == "shared_indexacao":
            # Emails com shared_role=indexacao
            and_conditions.append({"shared_role": "indexacao"})
    elif not can_see_all and user_email:
        # --- DEFAULT ISOLATION (backward compatibility) ---
        # Regras estritas de isolamento para utilizadores não-admin:
        # 1. Emails devem pertencer ao utilizador (created_by OU synced_for_user)
        # 2. O endereço do utilizador deve aparecer no FROM/TO
        # 3. Emails legados sem user_id (antigo sync global "geral") são BLOQUEADOS
        # 4. EXCEÇÃO: Utilizadores de roles com email partilhado (ex: indexacao)
        #    podem ver emails sincronizados via Gmail API para esse role
        # NOTA: admin/ceo/diretor podem ver TUDO (can_see_all = True)
        user_id_isolation = current_user["id"]
        user_role_isolation = current_user.get("role", "")

        # Verificar se o utilizador pertence a um role com email partilhado
        shared_role_config = None
        if user_role_isolation:
            shared_role_config = await db.shared_role_email_configs.find_one(
                {"role": user_role_isolation, "is_configured": True},
                {"_id": 0, "role": 1},
            )

        # Filtro de pertença: o email deve ter sido criado por este utilizador
        # OU sincronizado para a sua conta pessoal
        # OU sincronizado para o role partilhado do utilizador
        ownership_filter = {
            "$or": [
                {"created_by": user_id_isolation},
                {"synced_for_user": user_id_isolation},
                {"synced_for_user": user_email},
            ]
        }

        # Se o utilizador tem um role com email partilhado, incluir emails do role
        if shared_role_config:
            ownership_filter["$or"].append({"shared_role": user_role_isolation})

        if folder == "inbox":
            inbox_or = [
                {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
            ]
            # Se há conta selecionada, incluir também o email da conta partilhada
            if account_email and account_email != user_email:
                inbox_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$and": [ownership_filter, {"$or": inbox_or}]})
        elif folder == "sent":
            sent_or = [
                {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                {"created_by": user_id_isolation},
            ]
            if account_email and account_email != user_email:
                sent_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$or": [ownership_filter, {"$or": sent_or}]})
        elif folder == "drafts":
            # Rascunhos: criados pelo utilizador
            and_conditions.append({"created_by": user_id_isolation})
        elif folder in ("starred", "trash", "custom"):
            shared_or = [
                {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
            ]
            if account_email and account_email != user_email:
                shared_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
                shared_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$and": [ownership_filter, {"$or": shared_or}]})
    
    # === FILTRO DE PASTA ===
    if folder == "inbox":
        and_conditions.append({"direction": "received"})
        and_conditions.append({"status": {"$ne": "draft"}})
        and_conditions.append({"is_archived": False})
    elif folder == "sent":
        and_conditions.append({"direction": "sent"})
        and_conditions.append({"status": {"$ne": "draft"}})
        and_conditions.append({"is_archived": False})
    elif folder == "starred":
        and_conditions.append({"is_starred": True})
    elif folder == "trash":
        and_conditions.append({"is_archived": True})
    elif folder == "drafts":
        and_conditions.append({"status": "draft"})
    elif folder == "custom":
        if not custom_folder:
            raise HTTPException(status_code=400, detail="ID da pasta não especificado")
        and_conditions.append({"folder_id": custom_folder})
    
    # === FILTRO POR CONTA IMAP ===
    # Quando box=personal, os emails sao isolados por synced_for_user e o campo
    # account guarda o endereco IMAP real do utilizador (ex: joao@empresa.pt).
    # O filtro account=power/precision so faz sentido para box=general/shared.
    if account and box != "personal":
        and_conditions.append({
            "$or": [
                {"account": account},
                {"account": {"$exists": False}},
            ]
        })
    
    # === FILTRO POR LABEL ===
    if label:
        and_conditions.append({"labels": label})
    
    # === PESQUISA TEXTUAL ===
    if search:
        search = sanitize_string(search, max_length=200)
        and_conditions.append({
            "$or": [
                {"subject": {"$regex": search, "$options": "i"}},
                {"body": {"$regex": search, "$options": "i"}},
                {"from_email": {"$regex": search, "$options": "i"}},
                {"to_emails": {"$regex": search, "$options": "i"}},
            ]
        })
    
    # Montar query final
    if len(and_conditions) == 1:
        query = and_conditions[0]
    elif and_conditions:
        query = {"$and": and_conditions}
    else:
        query = {}
    
    logger.debug(f"User {user_email} querying box {box} with filter {query}")
    
    skip = (page - 1) * limit
    total = await db.emails.count_documents(query)
    
    logger.debug(f"User {user_email} box={box} => total={total}")
    
    logger.info(f"[Webmail List] folder={folder}, account={account}, user={user_email}, total={total}")
    
    emails = await db.emails.find(
        query,
        {"_id": 0, "body": 0, "body_html": 0}
    ).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)

    # Serialize _id to string and ensure id is always a string for frontend keying
    emails_serialized = []
    for email in emails:
        email = dict(email)
        if "_id" in email and email["_id"]:
            email["_id"] = str(email["_id"])
        if "id" in email and email["id"]:
            email["id"] = str(email["id"])
        emails_serialized.append(email)
    emails = emails_serialized

    # Contar não lidos para a pasta inbox (com isolamento de utilizador)
    unread_count = 0
    if folder == "inbox":
        unread_and = [
            {"direction": "received"},
            {"status": {"$ne": "draft"}},
            {"is_read": False},
            {"is_archived": False},
        ]
        # Aplicar box filter ao unread_count
        if box == "personal":
            unread_and.append({
                "$or": [
                    {"created_by": user_id},
                    {"synced_for_user": user_id},
                    {"synced_for_user": user_email},
                ]
            })
        elif box == "general":
            unread_and.append({"$or": [{"shared_role": "geral"}, {"is_general": True}]})
        elif box == "shared_indexacao":
            unread_and.append({"shared_role": "indexacao"})
        elif not can_see_all and user_email:
            # Default isolation (backward compat)
            user_id_unread = current_user["id"]
            unread_and.append({
                "$and": [
                    {"$or": [
                        {"created_by": user_id_unread},
                        {"synced_for_user": user_id_unread},
                        {"synced_for_user": user_email},
                    ]},
                    {"$or": [
                        {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                    ]},
                ]
            })
        if account and box != "personal":
            unread_and.append({
                "$or": [
                    {"account": account},
                    {"account": {"$exists": False}},
                ]
            })
        unread_count = await db.emails.count_documents({"$and": unread_and})
    
    # Enriquecer emails com nome do processo/cliente
    enriched = []
    for email in emails:
        e = await enrich_email(email)
        e["id"] = str(e.get("id", ""))
        # Preview: primeira linha do body (buscar sem os campos excluídos acima)
        body_preview = email.get("body", "")[:120]
        if len(body_preview) == 120:
            body_preview += "..."
        e["preview"] = body_preview
        enriched.append(e)
    
    return {
        "emails": enriched,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "unread_count": unread_count,
        "folder": folder
    }


@router.get("/webmail-stats")
async def webmail_stats(
    box: Optional[str] = Query(None, description="Caixa: personal, general, shared_indexacao"),
    current_user: dict = Depends(get_current_user)
):
    """
    Estatísticas de Webmail para o utilizador logado.
    
    Retorna contadores de emails não lidos, enviados hoje e rascunhos pendentes.
    Respeita o isolamento de dados: consultor/intermediário só vê os seus.
    Admin/CEO/Diretor vêem a caixa geral.
    
    BOX PARAM: filtra as estatísticas por caixa (personal, general, shared_indexacao).
    """
    from models.auth import UserRole
    
    user_email = (current_user.get("email") or "").lower().strip()
    user_role = current_user.get("role", "")
    user_id = current_user.get("id", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    
    # === BOX permission checks ===
    if box == "general":
        if user_role in (UserRole.CONSULTOR, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'geral' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail Stats] box=general, user={user_email}, role={user_role}")
    elif box == "shared_indexacao":
        if user_role not in (UserRole.ADMIN, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'shared_indexacao' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail Stats] box=shared_indexacao, user={user_email}, role={user_role}")
    
    # Base queries
    inbox_base = {
        "direction": "received",
        "status": {"$ne": "draft"},
        "is_archived": False,
    }
    sent_base = {
        "direction": "sent",
        "status": {"$ne": "draft"},
        "is_archived": False,
    }
    drafts_base = {
        "status": "draft",
        "is_archived": False,
    }
    
    # Apply box filter or default isolation
    if box == "personal":
        inbox_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
        sent_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
        drafts_base["created_by"] = user_id
    elif box == "general":
        inbox_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
        sent_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
        drafts_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
    elif box == "shared_indexacao":
        inbox_base["shared_role"] = "indexacao"
        sent_base["shared_role"] = "indexacao"
        drafts_base["shared_role"] = "indexacao"
    elif not can_see_all and user_email:
        # Apply user isolation (same query as webmail list for consistency)
        user_isolation_or = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
        inbox_base["$or"] = user_isolation_or
        sent_base["$or"] = user_isolation_or
        drafts_base["created_by"] = user_id
    
    # Unread count
    unread_query = {**inbox_base, "is_read": False}
    unread_count = await db.emails.count_documents(unread_query)
    
    # Sent today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    sent_today_query = {
        **sent_base,
        "sent_at": {"$gte": today_start}
    }
    sent_today_count = await db.emails.count_documents(sent_today_query)
    
    # Drafts count
    drafts_count = await db.emails.count_documents(drafts_base)
    
    # Full folder counts for sidebar badges
    inbox_count = await db.emails.count_documents(inbox_base)
    sent_count = await db.emails.count_documents(sent_base)
    
    # Starred count
    starred_base = {"is_starred": True, "is_archived": False}
    if box == "personal":
        starred_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    elif box == "general":
        starred_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
    elif box == "shared_indexacao":
        starred_base["shared_role"] = "indexacao"
    elif not can_see_all and user_email:
        starred_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    starred_count = await db.emails.count_documents(starred_base)
    
    # Trash count
    trash_base = {"is_archived": True}
    if box == "personal":
        trash_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    elif box == "general":
        trash_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
    elif box == "shared_indexacao":
        trash_base["shared_role"] = "indexacao"
    elif not can_see_all and user_email:
        trash_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    trash_count = await db.emails.count_documents(trash_base)
    
    return {
        "unread_count": unread_count,
        "sent_today_count": sent_today_count,
        "drafts_count": drafts_count,
        "folder_counts": {
            "inbox": inbox_count,
            "sent": sent_count,
            "starred": starred_count,
            "drafts": drafts_count,
            "trash": trash_count,
        }
    }


@router.post("/webmail/sync")
async def webmail_sync(
    account: Optional[str] = Query(None, description="Conta: precision ou power (None = todas)"),
    days: int = Query(7, ge=1, le=30, description="Dias para sincronizar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Sincronizar emails do IMAP para o Webmail (background).
    
    ISOLAMENTO DE DADOS:
    - admin/ceo/diretor: podem sincronizar contas globais (power, precision)
    - outros roles: BLOQUEADOS — devem usar POST /webmail/sync-user
      para sincronizar a sua caixa pessoal.
    
    Esta rota faz pull de TODOS os emails recentes das pastas INBOX e Enviados
    das contas GLOBAIS configuradas. Para isolamento, utilizadores comuns
    devem usar o endpoint /webmail/sync-user.
    """
    from models.auth import UserRole
    from services.background_jobs import BackgroundJobService, JobType
    
    # Bloquear sync global para utilizadores não-admin
    user_role = current_user.get("role", "")
    if user_role not in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR):
        raise HTTPException(
            status_code=403,
            detail="Sincronização global apenas disponível para administradores. Use /webmail/sync-user para sincronizar o seu email pessoal."
        )
    
    # Verificar contas configuradas primeiro
    accounts = await get_email_accounts_async()
    if not accounts:
        return {
            "success": False,
            "error": "Nenhuma conta de email configurada. Vá a Configurações > Email e configure pelo menos uma conta IMAP.",
            "accounts_found": 0
        }
    
    # Se account foi especificado, verificar se existe
    if account:
        matched = [a for a in accounts if a.name == account]
        if not matched:
            available = [a.name for a in accounts]
            return {
                "success": False,
                "error": f"Conta '{account}' não encontrada. Contas disponíveis: {available}",
                "accounts_found": len(accounts),
                "available_accounts": available
            }
    
    # Criar job em background
    job_service = BackgroundJobService()
    job_id = await job_service.create_job(
        job_type=JobType.EMAIL_SYNC,
        user_id=current_user["id"],
        user_email=current_user.get("email", ""),
        metadata={"account": account, "days": days}
    )
    
    # Executar sincronização em background
    async def run_sync():
        try:
            await job_service.update_progress(job_id, 0, 1, "A sincronizar emails...")
            result = await sync_webmail_emails(
                account_name=account,
                days=days,
                max_emails=150
            )
            # Extract summary
            synced = result.get("emails_synced", result.get("synced", 0))
            total = result.get("emails_found", result.get("total", 0))
            msg = f"Sincronização concluída: {synced} emails"
            if result.get("success") == False:
                await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
            else:
                await job_service.complete_job(job_id, {"synced": synced, "total": total, "details": result})
        except Exception as e:
            logger.error(f"Erro na sincronização webmail: {e}", exc_info=True)
            await job_service.fail_job(job_id, str(e))
    
    asyncio.create_task(run_sync())
    
    return {
        "success": True,
        "message": "Sincronização iniciada em background",
        "job_id": job_id,
        "status": "started"
    }


@router.post("/webmail/sync-user")
async def webmail_sync_user(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Sincronizar emails usando as credenciais do utilizador logado.
    
    Para roles com email partilhado (indexacao, suporte), usa as credenciais
    da conta partilhada do departamento em vez das credenciais pessoais.
    """
    from services.background_jobs import BackgroundJobService, JobType
    
    user_id = current_user["id"]
    user_role = get_effective_role(request, current_user)
    
    # === INDEXACAO / SUPORTE: usar conta partilhada do departamento ===
    if user_role in ("indexacao", "suporte"):
        # Tenta shared_role_email_configs primeiro, depois fallback para system_webmail (Bloco C)
        shared_config = await db.shared_role_email_configs.find_one(
            {"role": user_role, "is_configured": True},
            {"_id": 0}
        )
        if not shared_config:
            # Fallback: verificar system_webmail das Integrações (Bloco C)
            from services.system_config import get_system_config
            sys_config = await get_system_config()
            sys_webmail = sys_config.system_webmail
            if not (sys_webmail.imap_host and sys_webmail.email_user and sys_webmail.app_password):
                return {
                    "success": False,
                    "error": f"Configuração de email partilhada para {user_role} não encontrada. Configure em Definições > Integrações (Bloco C) ou contacte o administrador."
                }
        
        # Criar job em background com sync partilhado
        job_service = BackgroundJobService()
        job_id = await job_service.create_job(
            job_type=JobType.EMAIL_SYNC,
            user_id=user_id,
            user_email=current_user.get("email", ""),
            metadata={"sync_type": "shared_role", "role": user_role}
        )
        
        async def run_shared_sync():
            try:
                from services.email_service import sync_shared_role_emails
                await job_service.update_progress(job_id, 0, 1, f"A sincronizar emails partilhados ({user_role})...")
                result = await sync_shared_role_emails(user_role)
                if result.get("success") == False:
                    await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
                else:
                    synced = result.get("total_synced", 0)
                    await job_service.complete_job(job_id, {"synced": synced, "details": result})
            except Exception as e:
                logger.error(f"Erro na sincronização shared role emails: {e}", exc_info=True)
                await job_service.fail_job(job_id, str(e))
        
        asyncio.create_task(run_shared_sync())
        
        return {
            "success": True,
            "message": f"Sincronização de email partilhado ({user_role}) iniciada em background",
            "job_id": job_id,
        }
    
    # === UTILIZADORES NORMAIS: usar credenciais pessoais ===
    # Usar o resolver que suporta config individual, company e system (herança)
    active_role = user_role  # já obtido acima via get_effective_role
    from services.email_config_resolver import resolve_email_config_for_sync
    from services.auth import get_active_company_id_async
    active_company_id = await get_active_company_id_async(request, current_user)
    resolved = await resolve_email_config_for_sync(user_id, active_role=active_role, active_company_id=active_company_id)
    
    if not resolved:
        return {
            "success": False,
            "error": "Configuração de email não encontrada. Vá ao seu Perfil > Configuração de Webmail para configurar."
        }
    
    # Criar job em background
    job_service = BackgroundJobService()
    job_id = await job_service.create_job(
        job_type=JobType.EMAIL_SYNC,
        user_id=user_id,
        user_email=current_user.get("email", ""),
        metadata={"sync_type": "user_personal"}
    )
    
    async def run_user_sync():
        try:
            from services.email_service import sync_user_emails
            await job_service.update_progress(job_id, 0, 1, "A sincronizar emails pessoais...")
            # Passar o `resolved` (config já resolvida pelo resolver canónico) para
            # que sync_user_emails NÃO volte a ler user.email_config embebido (que
            # para configs multi-empresa é aninhado e fazia a sync falhar com
            # "Configuração de email não ativa").
            result = await sync_user_emails(user_id, resolved_config=resolved)
            if result.get("success") == False:
                await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
            else:
                synced = result.get("total_synced", 0)
                await job_service.complete_job(job_id, {"synced": synced, "details": result})
        except Exception as e:
            logger.error(f"Erro na sincronização user emails: {e}", exc_info=True)
            await job_service.fail_job(job_id, str(e))
    
    asyncio.create_task(run_user_sync())
    
    return {
        "success": True,
        "message": "Sincronização pessoal iniciada em background",
        "job_id": job_id,
    }


@router.get("/jobs/{job_id}")
async def get_email_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtém o estado de um job de sincronização de emails.
    
    Permite ao frontend fazer polling para saber quando a sincronização
    terminou e quantos emails foram sincronizados.
    """
    from services.background_jobs import BackgroundJobService
    
    job = await BackgroundJobService().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    # Verificar permissão: apenas o dono do job ou admin podem ver
    if job.get("user_id") != current_user.get("id") and current_user.get("role") not in ["admin", "ceo", "diretor"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    return job


@router.get("/process/{process_id}", response_model=List[EmailResponse])
async def get_process_emails(
    process_id: str,
    direction: Optional[EmailDirection] = Query(None, description="Filtrar por direção"),
    filter_by_user: bool = Query(False, description="Filtrar apenas emails onde o utilizador participou"),
    include_archived: bool = Query(False, description="Incluir emails arquivados"),
    force_refresh: bool = Query(False, description="Limpar emails em cache e re-sincronizar do IMAP"),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar emails de um processo.
    
    Retorna todos os emails associados ao processo (via process_id),
    ordenados por data descendente.
    
    Associação de emails a processos é feita automaticamente por:
    1. Smart Threading (herança de process_id via In-Reply-To / References)
    2. Tag Mágica [Proc-{id}] no assunto
    3. Associação manual pelo utilizador (botão Ligar a Processo no Webmail)
    
    Se force_refresh=True, limpa emails sincronizados em cache e
    dispara sincronização global (smart threading + tags aplicam-se automaticamente).
    """
    if force_refresh:
        # Limpar cache: apagar emails sincronizados (marcados com "Sincronizado de" nas notes)
        delete_result = await db.emails.delete_many({
            "process_id": process_id,
            "notes": {"$regex": "^Sincronizado de", "$options": "i"}
        })
        logger.info(f"Cache limpa para processo {process_id}: {delete_result.deleted_count} emails removidos")
        
        # Re-sincronizar do IMAP
        user_email = current_user.get("email")
        try:
            sync_result = await sync_emails_for_process(process_id, days=30, user_email=user_email)
            logger.info(f"Re-sync após limpeza de cache: {sync_result}")
        except Exception as e:
            logger.error(f"Erro na re-sync após limpeza de cache: {e}")
    
    # ── Query principal: emails com process_id directo ──
    base_conditions = [{"process_id": process_id}]

    # ── Fallback: emails sem process_id mas que envolvem o cliente do processo ──
    # Isto apanha emails enviados/recebidos (Sent/Drafts) que o Smart Threading
    # não associou automaticamente porque não tinham In-Reply-To ou tag [Proc-xxx].
    process_doc = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "client_email": 1, "monitored_emails": 1}
    )
    client_email = (process_doc or {}).get("client_email", "").lower().strip()
    monitored = (process_doc or {}).get("monitored_emails", [])

    if client_email or monitored:
        # Construir lista de endereços do cliente para matching
        client_emails = set()
        if client_email:
            client_emails.add(client_email)
        for me in monitored:
            if me and isinstance(me, str):
                client_emails.add(me.lower().strip())
        client_emails.discard("")

        if client_emails:
            email_match_or = []
            for ce in client_emails:
                escaped = re.escape(ce)
                email_match_or.extend([
                    {"from_email": {"$regex": f"^{escaped}$", "$options": "i"}},
                    {"to_emails": {"$regex": f"^{escaped}$", "$options": "i"}},
                ])

            # Só incluir se NÃO tiver process_id já (evitar duplicados)
            fallback_condition = {
                "$and": [
                    {"$or": [{"process_id": None}, {"process_id": {"$exists": False}}]},
                    {"$or": email_match_or},
                ]
            }
            base_conditions.append(fallback_condition)

    query = {"$or": base_conditions} if len(base_conditions) > 1 else base_conditions[0]

    if direction:
        query = {"$and": [query, {"direction": direction.value}]}

    if not include_archived:
        if "$and" in query:
            query["$and"].append({"is_archived": {"$ne": True}})
        else:
            query = {"$and": [query, {"is_archived": {"$ne": True}}]}

    if filter_by_user:
        user_email = current_user.get("email", "").lower()
        if user_email:
            user_filter = {
                "$or": [
                    {"from_email": {"$regex": user_email, "$options": "i"}},
                    {"to_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}},
                    {"cc_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}}
                ]
            }
            if "$and" in query:
                query["$and"].append(user_filter)
            else:
                query = {"$and": [query, user_filter]}

    emails = await db.emails.find(query, {"_id": 0}).sort("sent_at", -1).to_list(500)
    
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(EmailResponse(**enriched))
    
    return enriched_emails


@router.get("/stats/{process_id}")
async def get_email_stats(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter estatísticas de emails de um processo."""
    # Construir query com fallback por email do cliente (mesma lógica de get_process_emails)
    base_conditions = [{"process_id": process_id}]
    process_doc = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "client_email": 1, "monitored_emails": 1}
    )
    client_email_val = (process_doc or {}).get("client_email", "").lower().strip()
    monitored = (process_doc or {}).get("monitored_emails", [])
    if client_email_val or monitored:
        client_emails = set()
        if client_email_val:
            client_emails.add(client_email_val)
        for me in monitored:
            if me and isinstance(me, str):
                client_emails.add(me.lower().strip())
        client_emails.discard("")
        if client_emails:
            email_match_or = []
            for ce in client_emails:
                escaped = re.escape(ce)
                email_match_or.extend([
                    {"from_email": {"$regex": f"^{escaped}$", "$options": "i"}},
                    {"to_emails": {"$regex": f"^{escaped}$", "$options": "i"}},
                ])
            fallback_condition = {
                "$and": [
                    {"$or": [{"process_id": None}, {"process_id": {"$exists": False}}]},
                    {"$or": email_match_or},
                ]
            }
            base_conditions.append(fallback_condition)

    stats_query = {"$or": base_conditions} if len(base_conditions) > 1 else base_conditions[0]
    stats_query["is_archived"] = {"$ne": True}

    pipeline = [
        {"$match": stats_query},
        {"$group": {
            "_id": "$direction",
            "count": {"$sum": 1}
        }}
    ]

    results = await db.emails.aggregate(pipeline).to_list(10)

    stats = {
        "total": 0,
        "sent": 0,
        "received": 0,
        "unread": 0,
        "important": 0,
        "starred": 0
    }

    for r in results:
        if r["_id"] == "sent":
            stats["sent"] = r["count"]
        elif r["_id"] == "received":
            stats["received"] = r["count"]
        stats["total"] += r["count"]

    # Contar não lidos, importantes e estrelados
    stats["unread"] = await db.emails.count_documents({
        **stats_query, "is_read": False
    })
    stats["important"] = await db.emails.count_documents({
        **stats_query, "is_important": True
    })
    stats["starred"] = await db.emails.count_documents({
        **stats_query, "is_starred": True
    })

    return stats


@router.post("/sync/{process_id}")
async def sync_process_emails(
    process_id: str,
    background_tasks: BackgroundTasks,
    days: int = Query(30, description="Sincronizar emails dos últimos X dias"),
    blocking: bool = Query(False, description="Esperar pela sincronização (pode demorar)"),
    current_user: dict = Depends(get_current_user)
):
    """Sincronizar emails de um processo."""
    user_email = current_user.get("email")
    
    if blocking:
        result = await sync_emails_for_process(process_id, days, user_email=user_email)
        return result
    else:
        async def run_sync():
            """Executa a sincronização de emails em background para o processo.

            Atualiza ``_sync_status`` com o estado (running/completed/failed)
            para que o frontend possa fazer polling do progresso.

            Args:
                Nenhum parâmetro direto — usa variáveis do closure
                (process_id, days, user_email).

            Returns:
                None. Resultado é guardado em ``_sync_status[process_id]``.
            """
            try:
                _sync_status[process_id] = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
                result = await sync_emails_for_process(process_id, days, user_email=user_email)
                _sync_status[process_id] = {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": result
                }
            except Exception as e:
                logger.error(f"Erro na sincronização de emails para {process_id}: {e}")
                _sync_status[process_id] = {
                    "status": "error",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
        
        asyncio.create_task(run_sync())
        
        return {
            "success": True,
            "message": "Sincronização iniciada em background",
            "process_id": process_id,
            "status": "started"
        }


@router.get("/sync-status/{process_id}")
async def get_sync_status(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Verificar o status da sincronização de emails."""
    if process_id in _sync_status:
        return _sync_status[process_id]
    return {"status": "not_found", "message": "Nenhuma sincronização encontrada"}


@router.post("/associate")
async def associate_email_to_client(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Associar um email existente a um processo/cliente específico.

    SEGURANÇA: Não-admin só pode associar emails que lhe pertencem.
    """
    from models.auth import UserRole

    email_id = data.get("email_id")
    process_id = data.get("process_id")
    
    if not email_id or not process_id:
        raise HTTPException(status_code=400, detail="email_id e process_id são obrigatórios")
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "id": 1, "client_name": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = await db.emails.find_one(
        {"$or": [{"id": email_id}, {"message_id": email_id}]},
        {"_id": 0}
    )
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    # === ISOLAMENTO: verificar que o utilizador tem acesso ao email ===
    user_role = current_user.get("role", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)

    if not can_see_all:
        user_id = current_user["id"]
        is_owner = (
            email.get("created_by") == user_id
            or email.get("synced_for_user") == user_id
        )
        is_shared_role = (
            email.get("shared_role")
            and email.get("shared_role") == user_role
        )
        if not (is_owner or is_shared_role):
            raise HTTPException(status_code=403, detail="Sem permissão para associar este email")
    
    if email.get("process_id") == process_id:
        return {"success": True, "message": "Email já está associado a este processo"}
    
    now = datetime.now(timezone.utc).isoformat()
    await db.emails.update_one(
        {"id": email["id"]},
        {"$set": {
            "process_id": process_id,
            "associated_by": current_user["id"],
            "associated_at": now
        }}
    )
    
    logger.info(f"Email {email['id']} associado ao processo {process_id} por {current_user['email']}")
    
    return {
        "success": True,
        "message": f"Email associado ao cliente {process.get('client_name', process_id)}",
        "email_id": email["id"],
        "process_id": process_id
    }


@router.get("/search")
async def search_emails(
    q: str = Query(..., description="Termo de pesquisa"),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Pesquisar emails para associação manual.

    SEGURANÇA: Não-admin só pode pesquisar nos seus próprios emails.
    """
    from models.auth import UserRole

    if len(q) < 3:
        raise HTTPException(status_code=400, detail="Termo deve ter pelo menos 3 caracteres")

    # === ISOLAMENTO DE DADOS ===
    user_role = current_user.get("role", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)

    text_filter = {
        "$or": [
            {"subject": {"$regex": q, "$options": "i"}},
            {"from_email": {"$regex": q, "$options": "i"}},
            {"to_emails": {"$regex": q, "$options": "i"}},
            {"body": {"$regex": q, "$options": "i"}},
        ]
    }

    if can_see_all:
        query = text_filter
    else:
        user_id = current_user["id"]
        ownership_filter = {
            "$or": [
                {"created_by": user_id},
                {"synced_for_user": user_id},
            ]
        }
        # Incluir emails do role partilhado
        shared_config = await db.shared_role_email_configs.find_one(
            {"role": user_role, "is_configured": True}, {"_id": 0, "role": 1}
        )
        if shared_config:
            ownership_filter["$or"].append({"shared_role": user_role})

        query = {"$and": [ownership_filter, text_filter]}
    
    emails = await db.emails.find(
        query,
        {"_id": 0, "id": 1, "subject": 1, "from_email": 1, "to_emails": 1, "sent_at": 1, "process_id": 1}
    ).sort("sent_at", -1).limit(limit).to_list(limit)
    
    for email in emails:
        if email.get("process_id"):
            process = await db.processes.find_one(
                {"id": email["process_id"]},
                {"_id": 0, "client_name": 1}
            )
            if process:
                email["client_name"] = process.get("client_name")
    
    return {"emails": emails, "total": len(emails)}


@router.post("/send")
async def send_email_endpoint(
    payload: EmailSendRequest,
    request: Request,
    account: str = Query("power", description="Conta de email"),
    current_user: dict = Depends(get_current_user)
):
    """
    Enviar email através de uma das contas configuradas.
    
    ISOLAMENTO DE REMETENTE:
    - admin/ceo/diretor: podem usar contas globais (power, precision) OU pessoal
    - outros roles (consultor, intermediario, etc.): obrigatoriamente usam
      a conta pessoal configurada no seu perfil (email_config).
      Se não tiver email configurado, o envio é bloqueado.
    
    BOX SUPPORT (from_box):
    - indexacao: ao enviar, usa automaticamente a conta partilhada do role
    - general (from_box): CEO/admin/diretor podem enviar da caixa geral (shared_role=geral)
    """
    from models.auth import UserRole
    from services.email_config_resolver import resolve_email_config_for_sync

    # === PACOTE AL: Extração Imediata da Empresa e do Remetente Base ===
    # 1. active_company_id: tentar header direto primeiro (mais rápido),
    #    depois fallback para get_active_company_id_async.
    active_company_id = request.headers.get("x-company-id")
    if not active_company_id:
        try:
            from services.auth import get_active_company_id_async
            active_company_id = await get_active_company_id_async(request, current_user)
        except Exception:
            active_company_id = None

    user_role = current_user.get("role", "")
    can_use_global_accounts = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    from_box = payload.from_box
    from_email = current_user.get("email")  # Remetente Base

    # === indexacao role: auto-use shared email account ===
    if user_role == UserRole.INDEXACAO:
        shared_config = await db.shared_role_email_configs.find_one(
            {"role": UserRole.INDEXACAO, "is_configured": True},
            {"_id": 0, "email_address": 1, "email": 1},
        )
        if shared_config:
            shared_email_addr = shared_config.get("email_address") or shared_config.get("email", "")
            account = "personal"
            logger.info(f"[Send Email] indexacao user {current_user.get('email')}: using shared account {shared_email_addr}")
        else:
            resolved = await resolve_email_config_for_sync(
                current_user["id"],
                active_role=user_role,
                active_company_id=active_company_id
            )
            if not resolved:
                raise HTTPException(
                    status_code=403,
                    detail="Configuração de email partilhada para indexacao não encontrada. Contacte o administrador."
                )
            account = "personal"

    # === PACOTE AL: Forçar conta pessoal e Resolver a Config ===
    # from_box == "personal" OU utilizador não-admin → usar conta pessoal.
    elif from_box == "personal" or not can_use_global_accounts:
        account = "personal"

    # === from_box == "general": use shared geral account ===
    elif from_box == "general":
        if user_role not in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR):
            raise HTTPException(
                status_code=403,
                detail="Apenas admin, CEO e diretor podem enviar emails a partir da caixa geral."
            )
        account = "power"
        logger.info(f"[Send Email] user {current_user.get('email')} ({user_role}): sending from geral box (account={account})")

    # === PACOTE AL: Resolver config pessoal (exceto indexacao já tratado) ===
    # Resolve o from_email correto a partir da config do utilizador para a
    # empresa ativa. Isto garante que o email sai pela conta certa e que
    # o reply_to aponta para o email configurado.
    if account == "personal" and user_role != UserRole.INDEXACAO:
        try:
            resolved = await resolve_email_config_for_sync(
                current_user["id"],
                active_role=user_role,
                active_company_id=active_company_id
            )
        except Exception as e:
            logger.exception(f"[Send Email] Erro no resolver para user {current_user.get('email')}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao resolver configuração de email: {type(e).__name__}: {e}"
            )
        if not resolved:
            raise HTTPException(
                status_code=403,
                detail="Configuração de email não encontrada para esta empresa. Vá ao seu Perfil > Configuração de Webmail para configurar o seu email antes de enviar."
            )
        from_email = resolved.get("email_address") or from_email
        logger.info(f"[Send Email] Utilizador {current_user.get('email')} ({user_role}): conta pessoal (from_email={from_email}, empresa={active_company_id})")

    # Sanitize inputs before sending and DB insert
    to_emails = [e for e in (sanitize_email(e) for e in payload.to_emails) if e]
    cc_emails = None
    if payload.cc_emails:
        cc_emails = [e for e in (sanitize_email(e) for e in payload.cc_emails) if e]
    subject = sanitize_string(payload.subject, max_length=300)
    body = sanitize_string(payload.body, max_length=10000)
    # PACOTE AK: Sanitização e proteção do HTML — inline styles para imagens
    # evitam desformatação em clientes de email clássicos (Gmail/Outlook)
    body_html = payload.body_html
    if body_html:
        body_html = sanitize_html(body_html, allow_email_html=True)
        # Injetar max-width nas imagens para evitar desformatação em clientes de email
        body_html = body_html.replace('<img ', '<img style="max-width: 100%; height: auto;" ')

    if not to_emails:
        raise HTTPException(status_code=400, detail="Pelo menos um email destinatário válido é necessário")

    # ==== PROCESS TEMP ATTACHMENTS ====
    email_attachments = []
    temp_attachment_records = []  # Track for S3 move + cleanup
    temp_keys_to_cleanup = []

    if payload.attachment_ids:
        # Look up temp attachments from MongoDB
        temp_docs = await db.temp_attachments.find(
            {"id": {"$in": payload.attachment_ids}, "user_id": current_user["id"]},
            {"_id": 0}
        ).to_list(20)

        if len(temp_docs) != len(payload.attachment_ids):
            found_ids = {d["id"] for d in temp_docs}
            missing = [aid for aid in payload.attachment_ids if aid not in found_ids]
            logger.warning(f"Temp attachments not found: {missing}")
            # Continue with available attachments

        from services.s3_storage import s3_service

        for temp_doc in temp_docs:
            temp_key = temp_doc["temp_key"]
            file_name = temp_doc["file_name"]
            mime_type = temp_doc.get("mime_type", "application/octet-stream")

            try:
                # Download content from temp S3 path
                loop = asyncio.get_running_loop()
                content_bytes = await loop.run_in_executor(
                    None, lambda tk=temp_key: s3_service.get_file_content(tk)
                )
                if content_bytes:
                    email_attachments.append({
                        "filename": file_name,
                        "content_bytes": content_bytes,
                        "content_type": mime_type,
                    })
                    temp_attachment_records.append({
                        "id": temp_doc["id"],
                        "file_name": file_name,
                        "file_size": temp_doc.get("file_size", len(content_bytes)),
                        "mime_type": mime_type,
                        "temp_key": temp_key,
                    })
                    temp_keys_to_cleanup.append(temp_key)
                    logger.info(f"Temp attachment prepared for send: {file_name}")
                else:
                    logger.warning(f"Could not download temp attachment from S3: {temp_key}")
            except Exception as e:
                logger.error(f"Error downloading temp attachment {file_name}: {e}")

    # === EMPRESA ATIVA + from_email — já resolvidos no início (Pacote AL) ===
    # active_company_id: para a assinatura correta da empresa ativa.
    # from_email: remetente pessoal resolvido da config (não a conta geral).
    # reply_to: respostas vão para o email do utilizador, não para a conta geral.

    try:
        result = await send_email(
            account_name=account,
            to_emails=to_emails,
            subject=subject,
            body=body,
            body_html=body_html,
            cc_emails=cc_emails,
            process_id=payload.process_id,
            created_by=current_user["id"],
            attachments=email_attachments if email_attachments else None,
            active_company_id=active_company_id,
            from_email=from_email,
            reply_to=from_email,
        )
    except Exception as e:
        logger.exception(f"[Send Email] Erro ao chamar send_email: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao enviar email: {type(e).__name__}: {e}"
        )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))

    # ==== MOVE ATTACHMENTS FROM TEMP TO PERMANENT + UPDATE EMAIL DOC ====
    if temp_attachment_records and payload.process_id:
        from services.s3_storage import s3_service

        # Find the most recently created sent email for this user+process
        sent_email = await db.emails.find_one(
            {
                "process_id": payload.process_id,
                "created_by": current_user["id"],
                "direction": "sent",
            },
            sort=[("sent_at", -1)],
        )

        if sent_email:
            permanent_attachments = []
            for att_rec in temp_attachment_records:
                permanent_s3_key = f"Emails/{sent_email['id']}/{att_rec['file_name']}"
                try:
                    loop = asyncio.get_running_loop()
                    moved = await loop.run_in_executor(
                        None,
                        lambda sk=att_rec["temp_key"], pk=permanent_s3_key: s3_service.rename_file(sk, pk)
                    )
                    if moved:
                        logger.info(f"Attachment moved: {att_rec['temp_key']} -> {permanent_s3_key}")
                    else:
                        logger.warning(f"Failed to move attachment: {att_rec['temp_key']}")
                        permanent_s3_key = att_rec["temp_key"]  # Keep temp key as fallback
                except Exception as e:
                    logger.error(f"Error moving attachment {att_rec['temp_key']}: {e}")
                    permanent_s3_key = att_rec["temp_key"]

                permanent_attachments.append({
                    "id": att_rec["id"],
                    "filename": att_rec["file_name"],
                    "file_name": att_rec["file_name"],
                    "size": att_rec["file_size"],
                    "content_type": att_rec["mime_type"],
                    "s3_key": permanent_s3_key,
                })

            # Update email document with permanent attachment metadata
            existing_attachments = sent_email.get("attachments", [])
            await db.emails.update_one(
                {"id": sent_email["id"]},
                {"$set": {"attachments": existing_attachments + permanent_attachments}}
            )

        # Clean up temp attachment metadata from MongoDB
        await db.temp_attachments.delete_many({"id": {"$in": [r["id"] for r in temp_attachment_records]}})

        # Clean up temp files from S3 (for any that weren't moved)
        from services.s3_storage import s3_service
        for temp_key in temp_keys_to_cleanup:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda tk=temp_key: s3_service.delete_file(tk))
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {temp_key}: {e}")

    result["attachments_sent"] = len(email_attachments)
    return result


# ==== RASCUNHOS AUTOMÁTICOS (Auto-Draft) ====

@router.get("/drafts")
async def list_auto_drafts(
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar rascunhos automáticos pendentes.
    Admin/CEO veem todos, outros só os dos seus processos.
    """
    drafts = await get_pending_drafts(
        user_id=current_user["id"],
        user_role=current_user["role"],
        limit=limit,
    )
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return {"drafts": drafts, "stats": stats}


@router.get("/drafts/stats")
async def auto_drafts_stats(
    current_user: dict = Depends(get_current_user)
):
    """Obter estatísticas de rascunhos automáticos pendentes."""
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return stats


@router.put("/drafts/{draft_id}")
async def edit_auto_draft(
    draft_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Editar um rascunho automático (subject, body, to_emails)."""
    # Sanitize user inputs before passing to service
    if "subject" in data and data["subject"]:
        data["subject"] = sanitize_string(data["subject"], max_length=300)
    if "body" in data and data["body"]:
        data["body"] = sanitize_string(data["body"], max_length=10000)
    if "to_emails" in data and data["to_emails"]:
        data["to_emails"] = [e for e in (sanitize_email(e) for e in data["to_emails"]) if e]

    result = await update_draft(draft_id, data)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Erro ao atualizar"))
    return result


@router.post("/drafts/{draft_id}/send")
async def send_auto_draft(
    draft_id: str,
    account: str = Query("power", description="Conta de email (power/precision)"),
    current_user: dict = Depends(get_current_user)
):
    """Enviar um rascunho automático."""
    result = await send_draft(
        draft_id=draft_id,
        user_id=current_user["id"],
        account=account,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao enviar"))
    return result


@router.delete("/drafts/{draft_id}")
async def delete_auto_draft(
    draft_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Descartar (eliminar) um rascunho automático."""
    result = await discard_draft(draft_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Rascunho não encontrado"))
    return result


@router.post("/drafts/create")
async def manually_create_draft(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Criar manualmente um rascunho automático para um documento em falta.
    Útil quando o admin quer gerar um rascunho para um processo específico.
    """
    process_id = data.get("process_id")
    doc_type = data.get("doc_type")

    if not process_id or not doc_type:
        raise HTTPException(status_code=400, detail="process_id e doc_type são obrigatórios")

    # Obter dados do processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    result = await create_missing_doc_draft(
        process_id=process_id,
        client_name=process.get("client_name", ""),
        missing_doc_type=doc_type,
        process_number=process.get("process_number", ""),
    )

    return result


# ==== ROTAS CRUD GENÉRICAS ====

@router.post("", response_model=EmailResponse)
async def create_email_record(
    email_data: EmailCreate,
    current_user: dict = Depends(get_current_user)
):
    """Registar um email no histórico."""
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Sanitize inputs before DB insert
    from_email = sanitize_email(email_data.from_email)
    to_emails = [e for e in (sanitize_email(e) for e in email_data.to_emails) if e]
    cc_emails = [e for e in (sanitize_email(e) for e in (email_data.cc_emails or [])) if e]
    bcc_emails = [e for e in (sanitize_email(e) for e in (email_data.bcc_emails or [])) if e]
    subject = sanitize_string(email_data.subject, max_length=300)
    body = sanitize_string(email_data.body, max_length=10000)
    notes = sanitize_string(email_data.notes, max_length=1000) if email_data.notes else None

    email = {
        "id": email_id,
        "process_id": email_data.process_id,
        "direction": email_data.direction.value,
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": subject,
        "body": body,
        "body_html": email_data.body_html,
        "attachments": [a.dict() for a in (email_data.attachments or [])],
        "status": email_data.status.value,
        "sent_at": email_data.sent_at or now,
        "created_at": now,
        "created_by": current_user["id"],
        "notes": notes,
        "is_important": False,
        "is_read": True,
        "is_starred": False,
        "is_archived": False,
        "labels": []
    }
    
    await db.emails.insert_one(email)
    logger.info(f"Email registado: {email_id} para processo {email_data.process_id}")
    
    enriched = await enrich_email(email)
    return EmailResponse(**enriched)


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Obter detalhes de um email.

    SEGURANÇA: Não-admin só pode ver emails que lhe pertencem.
    Verifica created_by, synced_for_user ou shared_role.
    Usa o effective_role (X-Active-Role) para determinar can_see_all.
    """
    from models.auth import UserRole
    from services.auth import get_effective_role

    email = await db.emails.find_one({"id": email_id}, {"_id": 0})

    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    # === ISOLAMENTO DE DADOS ===
    # PACOTE AU: usar effective_role (X-Active-Role) em vez do role primário
    user_role = get_effective_role(request, current_user)
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)

    if not can_see_all:
        user_id = current_user["id"]
        user_email = (current_user.get("email") or "").lower().strip()

        # Verificar se o utilizador tem acesso a este email
        is_owner = (
            email.get("created_by") == user_id
            or email.get("synced_for_user") == user_id
        )
        is_shared_role = (
            email.get("shared_role")
            and email.get("shared_role") == user_role
        )
        is_in_conversation = False
        if user_email:
            from_emails = email.get("from_email") or ""
            to_emails = email.get("to_emails") or []
            is_in_conversation = (
                user_email in from_emails.lower()
                or any(user_email in addr.lower() for addr in to_emails)
            )

        if not (is_owner or is_shared_role or is_in_conversation):
            raise HTTPException(status_code=403, detail="Sem permissão para ver este email")

    enriched = await enrich_email(email)

    try:
        return EmailResponse(**enriched)
    except Exception as e:
        logger.error(f"Erro ao validar email {email_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar email {email_id}: {str(e)}"
        )


@router.put("/{email_id}", response_model=EmailResponse)
async def update_email(
    email_id: str,
    email_data: EmailUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Actualizar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if email_data.subject is not None:
        update_data["subject"] = sanitize_string(email_data.subject, max_length=300)
    if email_data.body is not None:
        update_data["body"] = sanitize_string(email_data.body, max_length=10000)
    if email_data.notes is not None:
        update_data["notes"] = sanitize_string(email_data.notes, max_length=1000)
    if email_data.status is not None:
        update_data["status"] = email_data.status.value
    if email_data.is_important is not None:
        update_data["is_important"] = email_data.is_important
    if email_data.is_read is not None:
        update_data["is_read"] = email_data.is_read
    if email_data.is_starred is not None:
        update_data["is_starred"] = email_data.is_starred
    if email_data.is_archived is not None:
        update_data["is_archived"] = email_data.is_archived
    if email_data.labels is not None:
        update_data["labels"] = email_data.labels
    
    if update_data:
        await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    updated_email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    enriched = await enrich_email(updated_email)

    try:
        return EmailResponse(**enriched)
    except Exception as e:
        logger.error(f"Erro ao validar email {email_id} após update: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar email {email_id}: {str(e)}"
        )


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar registo de email (MongoDB + mover para Trash no IMAP server)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    # === IMAP BIDIRECTIONAL SYNC: Move to Trash on IMAP server (instead of permanent delete) ===
    message_id = email.get("message_id")
    if message_id:
        try:
            account_value = email.get("account", "")
            synced_for_user = email.get("synced_for_user")
            email_account = await _get_email_account_for_email(account_value, synced_for_user)
            if email_account:
                folder = "INBOX" if email.get("direction") == "received" else "Sent"
                imap_result = await imap_move_to_trash(email_account, message_id, folder)
                if imap_result.get("success"):
                    trash_folder = imap_result.get("trash_folder")
                    fallback = imap_result.get("fallback")
                    if trash_folder:
                        logger.info(f"[IMAP Sync] Email {email_id} movido para '{trash_folder}' no IMAP")
                    elif fallback:
                        logger.warning(f"[IMAP Sync] Email {email_id} fallback expunge (Trash não encontrado)")
                else:
                    logger.warning(f"[IMAP Sync] Falha ao mover email para Trash: {imap_result.get('error')}")
        except Exception as imap_err:
            logger.warning(f"[IMAP Sync] Erro ao mover email para Trash: {imap_err}")
    
    # Soft-delete — mark as archived (appears in Trash folder)
    await db.emails.update_one(
        {"id": email_id},
        {"$set": {"is_archived": True, "archived_at": datetime.now(timezone.utc).isoformat()}}
    )
    logger.info(f"Email {email_id} movido para o Lixo por {current_user['name']}")
    
    return {"success": True, "message": "Email movido para o Lixo"}


@router.delete("/{email_id}/permanent")
async def permanently_delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Elimina permanentemente um email (apenas da pasta Lixo)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    if not email.get("is_archived"):
        raise HTTPException(status_code=400, detail="Apenas emails no Lixo podem ser eliminados permanentemente")
    
    await db.emails.delete_one({"id": email_id})
    logger.info(f"Email {email_id} permanentemente eliminado por {current_user['name']}")
    
    return {"success": True, "message": "Email permanentemente eliminado"}


# ==== GESTÃO DE EMAILS MONITORIZADOS ====

@router.get("/monitored/{process_id}")
async def get_monitored_emails(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter lista de emails monitorizados de um processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "client_email": 1, "monitored_emails": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return {
        "client_email": process.get("client_email"),
        "monitored_emails": process.get("monitored_emails", [])
    }


@router.post("/monitored/{process_id}")
async def add_monitored_email(
    process_id: str,
    email: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Adicionar email à lista de monitorizados."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = sanitize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="Email inválido")
    
    monitored = process.get("monitored_emails", [])
    
    if email in monitored or email == process.get("client_email", "").lower():
        raise HTTPException(status_code=400, detail="Email já está na lista")
    
    monitored.append(email)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"monitored_emails": monitored}}
    )
    
    logger.info(f"Email {email} adicionado à monitorização do processo {process_id}")
    
    return {
        "success": True,
        "monitored_emails": monitored
    }


@router.delete("/monitored/{process_id}/{email}")
async def remove_monitored_email(
    process_id: str,
    email: str,
    current_user: dict = Depends(get_current_user)
):
    """Remover email da lista de monitorizados."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = email.lower().strip()
    monitored = process.get("monitored_emails", [])
    
    if email not in monitored:
        raise HTTPException(status_code=404, detail="Email não encontrado na lista")
    
    monitored.remove(email)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"monitored_emails": monitored}}
    )
    
    logger.info(f"Email {email} removido da monitorização do processo {process_id}")
    
    return {
        "success": True,
        "monitored_emails": monitored
    }
