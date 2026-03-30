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

from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import Response

from database import db
from models.email import (
    EmailCreate, EmailUpdate, EmailResponse, EmailDirection, EmailStatus,
    EmailMarkType, EmailTemplateCreate, EmailTemplateResponse, EmailFilter
)
from services.auth import get_current_user
from services.email_service import sync_emails_for_process, send_email, test_email_connection, get_email_accounts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

# Armazenar status de sincronizações em progresso
_sync_status = {}


async def enrich_email(email: dict) -> dict:
    """Adicionar nomes ao email."""
    # Nome do processo/cliente
    if email.get("process_id"):
        process = await db.processes.find_one(
            {"id": email["process_id"]},
            {"_id": 0, "client_name": 1}
        )
        if process:
            email["client_name"] = process.get("client_name", "")
    
    # Nome de quem criou
    if email.get("created_by"):
        user = await db.users.find_one(
            {"id": email["created_by"]},
            {"_id": 0, "name": 1}
        )
        if user:
            email["created_by_name"] = user.get("name", "")
    
    return email


# ==== MARCAÇÃO DE EMAILS ====

@router.post("/{email_id}/mark")
async def mark_email(
    email_id: str,
    mark_type: EmailMarkType = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """
    Marcar um email como importante, lido, etc.
    
    Tipos de marcação:
    - important: Marcar como importante
    - read: Marcar como lido
    - unread: Marcar como não lido
    - starred: Marcar com estrela
    - archived: Arquivar
    - spam: Marcar como spam
    """
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if mark_type == EmailMarkType.IMPORTANT:
        update_data["is_important"] = True
    elif mark_type == EmailMarkType.READ:
        update_data["is_read"] = True
    elif mark_type == EmailMarkType.UNREAD:
        update_data["is_read"] = False
    elif mark_type == EmailMarkType.STARRED:
        update_data["is_starred"] = True
    elif mark_type == EmailMarkType.ARCHIVED:
        update_data["is_archived"] = True
    elif mark_type == EmailMarkType.SPAM:
        update_data["is_spam"] = True
    
    await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    logger.info(f"Email {email_id} marcado como {mark_type.value} por {current_user['email']}")
    
    return {
        "success": True,
        "email_id": email_id,
        "mark_type": mark_type.value
    }


@router.delete("/{email_id}/mark/{mark_type}")
async def unmark_email(
    email_id: str,
    mark_type: EmailMarkType,
    current_user: dict = Depends(get_current_user)
):
    """Remover marcação de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if mark_type == EmailMarkType.IMPORTANT:
        update_data["is_important"] = False
    elif mark_type == EmailMarkType.STARRED:
        update_data["is_starred"] = False
    elif mark_type == EmailMarkType.ARCHIVED:
        update_data["is_archived"] = False
    
    await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    return {"success": True, "email_id": email_id, "removed": mark_type.value}


# ==== LABELS/ETIQUETAS ====

@router.post("/{email_id}/labels")
async def add_email_label(
    email_id: str,
    label: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Adicionar etiqueta ao email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    labels = email.get("labels", [])
    if label not in labels:
        labels.append(label)
        await db.emails.update_one(
            {"id": email_id},
            {"$set": {"labels": labels, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {"success": True, "labels": labels}


@router.delete("/{email_id}/labels/{label}")
async def remove_email_label(
    email_id: str,
    label: str,
    current_user: dict = Depends(get_current_user)
):
    """Remover etiqueta do email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    labels = email.get("labels", [])
    if label in labels:
        labels.remove(label)
        await db.emails.update_one(
            {"id": email_id},
            {"$set": {"labels": labels, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {"success": True, "labels": labels}


# ==== ANEXOS ====

@router.get("/{email_id}/attachments")
async def get_email_attachments(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Listar anexos de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0, "attachments": 1})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    return {"attachments": email.get("attachments", [])}


@router.get("/{email_id}/attachments/{attachment_id}")
async def download_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download de anexo."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == attachment_id), None)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    
    # Se tiver URL externa, redirecionar
    if attachment.get("url"):
        return {"redirect_url": attachment["url"]}
    
    # Se tiver conteúdo em base64
    if attachment.get("content"):
        content = base64.b64decode(attachment["content"])
        return Response(
            content=content,
            media_type=attachment.get("content_type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{attachment["filename"]}"'
            }
        )
    
    raise HTTPException(status_code=404, detail="Conteúdo do anexo não disponível")


@router.get("/{email_id}/attachments/{attachment_id}/preview")
async def preview_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Preview de anexo (para imagens e PDFs)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == attachment_id), None)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    
    content_type = attachment.get("content_type", "")
    
    # Verificar se é previewable
    previewable_types = ["image/", "application/pdf", "text/"]
    if not any(pt in content_type for pt in previewable_types):
        raise HTTPException(status_code=400, detail="Este tipo de ficheiro não suporta preview")
    
    # Se tiver preview_url
    if attachment.get("preview_url"):
        return {"preview_url": attachment["preview_url"]}
    
    # Se tiver conteúdo em base64
    if attachment.get("content"):
        content = base64.b64decode(attachment["content"])
        return Response(
            content=content,
            media_type=content_type
        )
    
    raise HTTPException(status_code=404, detail="Preview não disponível")


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
    
    # Filtro por direção
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
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Listar templates de resposta rápida."""
    query = {}
    if category:
        query["category"] = category
    
    templates = await db.email_templates.find(
        query,
        {"_id": 0}
    ).sort("usage_count", -1).to_list(50)
    
    return templates


@router.post("/templates", response_model=EmailTemplateResponse)
async def create_email_template(
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Criar novo template de resposta."""
    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    template_doc = {
        "id": template_id,
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
        "category": template.category,
        "is_default": template.is_default,
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
    """Atualizar template de resposta."""
    existing = await db.email_templates.find_one({"id": template_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    update_data = {
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
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


# ==== ROTAS ESPECÍFICAS (devem vir antes das genéricas) ====

@router.get("/test-connection")
async def test_email_connections(
    account: Optional[str] = Query(None, description="Conta específica (precision, power) ou todas"),
    current_user: dict = Depends(get_current_user)
):
    """Testar conexão com as contas de email."""
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


@router.get("/process/{process_id}", response_model=List[EmailResponse])
async def get_process_emails(
    process_id: str,
    direction: Optional[EmailDirection] = Query(None, description="Filtrar por direção"),
    filter_by_user: bool = Query(False, description="Filtrar apenas emails onde o utilizador participou"),
    include_archived: bool = Query(False, description="Incluir emails arquivados"),
    current_user: dict = Depends(get_current_user)
):
    """Listar emails de um processo."""
    query = {"process_id": process_id}
    
    if direction:
        query["direction"] = direction.value
    
    if not include_archived:
        query["is_archived"] = {"$ne": True}
    
    if filter_by_user:
        user_email = current_user.get("email", "").lower()
        if user_email:
            query["$or"] = [
                {"from_email": {"$regex": user_email, "$options": "i"}},
                {"to_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}},
                {"cc_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}}
            ]
    
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
    pipeline = [
        {"$match": {"process_id": process_id, "is_archived": {"$ne": True}}},
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
        "process_id": process_id,
        "is_read": False,
        "is_archived": {"$ne": True}
    })
    stats["important"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_important": True
    })
    stats["starred"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_starred": True
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
    """Associar um email existente a um processo/cliente específico."""
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
    """Pesquisar emails para associação manual."""
    if len(q) < 3:
        raise HTTPException(status_code=400, detail="Termo deve ter pelo menos 3 caracteres")
    
    query = {
        "$or": [
            {"subject": {"$regex": q, "$options": "i"}},
            {"from_email": {"$regex": q, "$options": "i"}}
        ]
    }
    
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
    to_emails: List[str],
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    account: str = Query("precision", description="Conta de email"),
    process_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Enviar email através de uma das contas configuradas."""
    result = await send_email(
        account_name=account,
        to_emails=to_emails,
        subject=subject,
        body=body,
        body_html=body_html,
        cc_emails=cc_emails,
        process_id=process_id,
        created_by=current_user["id"]
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))
    
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
    
    email = {
        "id": email_id,
        "process_id": email_data.process_id,
        "direction": email_data.direction.value,
        "from_email": email_data.from_email,
        "to_emails": email_data.to_emails,
        "cc_emails": email_data.cc_emails or [],
        "bcc_emails": email_data.bcc_emails or [],
        "subject": email_data.subject,
        "body": email_data.body,
        "body_html": email_data.body_html,
        "attachments": [a.dict() for a in (email_data.attachments or [])],
        "status": email_data.status.value,
        "sent_at": email_data.sent_at or now,
        "created_at": now,
        "created_by": current_user["id"],
        "notes": email_data.notes,
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
    current_user: dict = Depends(get_current_user)
):
    """Obter detalhes de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    enriched = await enrich_email(email)
    return EmailResponse(**enriched)


@router.put("/{email_id}", response_model=EmailResponse)
async def update_email(
    email_id: str,
    email_data: EmailUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if email_data.subject is not None:
        update_data["subject"] = email_data.subject
    if email_data.body is not None:
        update_data["body"] = email_data.body
    if email_data.notes is not None:
        update_data["notes"] = email_data.notes
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
    return EmailResponse(**enriched)


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    await db.emails.delete_one({"id": email_id})
    logger.info(f"Email {email_id} eliminado por {current_user['name']}")
    
    return {"success": True, "message": "Email eliminado"}


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
    
    email = email.lower().strip()
    if not email or "@" not in email:
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


# ==== ENVIO DE DOCUMENTAÇÃO PARA BALCÕES ====

@router.get("/document-recipients")
async def get_document_recipients(
    current_user: dict = Depends(get_current_user)
):
    """
    Obter lista de destinatários disponíveis para envio de documentação.
    Apenas Admin e CEO podem editar as configurações.
    """
    from services.system_config import get_system_config
    
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        return {
            "enabled": False,
            "recipients": [],
            "email_template": None,
            "default_to": None,
            "default_to_name": None
        }
    
    # Parse recipients JSON
    recipients = []
    if doc_config.recipients:
        try:
            import json
            recipients = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            recipients = []
    
    return {
        "enabled": True,
        "recipients": recipients,
        "email_template": doc_config.email_template,
        "default_to": doc_config.default_to,
        "default_to_name": doc_config.default_to_name,
        "can_edit": current_user["role"] in ["admin", "ceo"]
    }


@router.post("/send-documentation/{process_id}")
async def send_documentation_email(
    process_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Enviar documentação do processo para balcões/bancos.
    
    Body:
    - document_ids: Lista de IDs dos documentos a enviar
    - bcc_recipients: Lista de emails BCC (destinatários selecionados)
    - cc_emails: Lista de emails CC (opcional)
    - custom_message: Mensagem personalizada (opcional, apenas admin/ceo)
    
    Validações:
    - Não enviar para bancos onde cliente tem conta ativa
    - Não enviar para bancos onde cliente fez simulação
    """
    from services.system_config import get_system_config
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Obter configuração
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        raise HTTPException(status_code=400, detail="Envio de documentação não está activado")
    
    # Dados do request
    document_ids = data.get("document_ids", [])
    bcc_recipients = data.get("bcc_recipients", [])
    cc_emails = data.get("cc_emails", [])
    custom_message = data.get("custom_message")
    
    if not document_ids:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um documento")
    
    if not bcc_recipients:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um destinatário")
    
    # Validar destinatários contra contas ativas e simulações
    financial_data = process.get("financial_data", {}) or {}
    bancos_creditos = financial_data.get("bancos_creditos", []) or []
    bancos_simulacoes = financial_data.get("bancos_simulacoes", []) or []
    
    # Normalizar nomes para comparação
    def normalize_bank_name(name):
        return name.lower().strip() if name else ""
    
    blocked_banks = [normalize_bank_name(b) for b in bancos_creditos + bancos_simulacoes]
    
    # Parse recipients para validar
    recipients_list = []
    if doc_config.recipients:
        try:
            import json
            recipients_list = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Validar cada BCC recipient
    validated_bcc = []
    warnings = []
    
    for bcc_email in bcc_recipients:
        # Encontrar o destinatário na lista para obter o nome
        recipient_info = next(
            (r for r in recipients_list if r.get("email", "").lower() == bcc_email.lower()),
            {"name": bcc_email, "email": bcc_email}
        )
        
        # Verificar se está bloqueado
        recipient_name = normalize_bank_name(recipient_info.get("name", ""))
        is_blocked = any(blocked in recipient_name or recipient_name in blocked for blocked in blocked_banks)
        
        if is_blocked:
            warnings.append(f"⚠️ {recipient_info.get('name', bcc_email)}: Cliente tem conta ativa ou simulação neste banco")
        else:
            validated_bcc.append(bcc_email)
    
    if warnings:
        logger.warning(f"Destinatários bloqueados para processo {process_id}: {warnings}")
    
    if not validated_bcc:
        raise HTTPException(
            status_code=400, 
            detail="Nenhum destinatário válido. O cliente tem contas ativas ou simulações em todos os bancos selecionados."
        )
    
    # Obter documentos
    documents = await db.documents.find(
        {"id": {"$in": document_ids}, "process_id": process_id},
        {"_id": 0}
    ).to_list(100)
    
    if not documents:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado")
    
    # Preparar lista de documentos para o email
    documents_list = "\n".join([
        f"- {doc.get('original_name', doc.get('filename', 'Documento'))}" 
        for doc in documents
    ])
    
    # Preparar template do email
    email_template = doc_config.email_template or """Prezados,

Segue em anexo a documentação do cliente:

**Cliente:** {client_name}
**NIF:** {client_nif}
**Processo:** #{process_number}

**Documentos enviados:**
{documents_list}

Esta documentação foi enviada através do sistema PowerCell.

Com os melhores cumprimentos,
{sender_name}
{sender_email}"""
    
    # Substituir variáveis
    client_name = process.get("client_name", "N/A")
    personal_data = process.get("personal_data", {}) or {}
    client_nif = personal_data.get("nif", process.get("client_nif", "N/A"))
    process_number = process.get("process_number", "N/A")
    
    email_body = email_template.format(
        client_name=client_name,
        client_nif=client_nif,
        process_number=process_number,
        documents_list=documents_list,
        sender_name=current_user.get("name", ""),
        sender_email=current_user.get("email", "")
    )
    
    # Se admin/CEO enviou mensagem personalizada, usar essa
    if custom_message and current_user["role"] in ["admin", "ceo"]:
        email_body = custom_message.format(
            client_name=client_name,
            client_nif=client_nif,
            process_number=process_number,
            documents_list=documents_list,
            sender_name=current_user.get("name", ""),
            sender_email=current_user.get("email", "")
        )
    
    # Preparar destinatários
    to_emails = [doc_config.default_to] if doc_config.default_to else [current_user["email"]]
    subject = f"Documentação - {client_name} (Processo #{process_number})"
    
    # Enviar email
    result = await send_email(
        account_name="power",  # Usar conta Power Real Estate
        to_emails=to_emails,
        subject=subject,
        body=email_body,
        cc_emails=cc_emails if cc_emails else None,
        bcc_emails=validated_bcc,
        process_id=process_id,
        created_by=current_user["id"]
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))
    
    # Registar envio no histórico
    email_record = {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "direction": "sent",
        "from_email": current_user["email"],
        "to_emails": to_emails,
        "cc_emails": cc_emails or [],
        "bcc_emails": validated_bcc,
        "subject": subject,
        "body": email_body,
        "attachments": [{"id": doc.get("id"), "filename": doc.get("original_name", doc.get("filename"))} for doc in documents],
        "status": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "notes": f"Documentação enviada para {len(validated_bcc)} destinatário(s)",
        "is_important": False,
        "is_read": True,
        "is_starred": False,
        "is_archived": False,
        "labels": ["documentação"]
    }
    
    await db.emails.insert_one(email_record)
    
    logger.info(f"Documentação enviada para processo {process_id} por {current_user['email']}: {len(validated_bcc)} destinatários")
    
    return {
        "success": True,
        "message": f"Documentação enviada com sucesso para {len(validated_bcc)} destinatário(s)",
        "warnings": warnings,
        "sent_to": validated_bcc,
        "email_id": email_record["id"]
    }
