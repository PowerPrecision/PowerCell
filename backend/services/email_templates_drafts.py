"""Templates de resposta, notificações unread e auto-drafts.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from models.email import EmailTemplateCreate, EmailTemplateResponse
from services.email_draft_service import (
    get_pending_drafts,
    get_draft_stats,
    update_draft,
    send_draft,
    discard_draft,
    create_missing_doc_draft,
)
from utils.input_sanitization import sanitize_string, sanitize_email

logger = logging.getLogger(__name__)

async def run_get_email_templates(request: Request, current_user: dict, category: Optional[str] = None):
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


async def run_create_email_template(template: EmailTemplateCreate, request: Request, current_user: dict):
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


async def run_update_email_template(template_id: str, template: EmailTemplateCreate, current_user: dict):
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


async def run_delete_email_template(template_id: str, current_user: dict):
    """Eliminar template de resposta."""
    result = await db.email_templates.delete_one({"id": template_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"success": True}


async def run_use_template(template_id: str, process_id: str, current_user: dict):
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


async def run_get_unread_notifications(current_user: dict):
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


async def run_list_auto_drafts(current_user: dict, limit: int = 20):
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


async def run_auto_drafts_stats(current_user: dict):
    """Obter estatísticas de rascunhos automáticos pendentes."""
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return stats


async def run_edit_auto_draft(draft_id: str, data: dict, current_user: dict):
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


async def run_send_auto_draft(draft_id: str, current_user: dict, account: str = "power"):
    """Enviar um rascunho automático."""
    result = await send_draft(
        draft_id=draft_id,
        user_id=current_user["id"],
        account=account,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao enviar"))
    return result


async def run_delete_auto_draft(draft_id: str, current_user: dict):
    """Descartar (eliminar) um rascunho automático."""
    result = await discard_draft(draft_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Rascunho não encontrado"))
    return result


async def run_manually_create_draft(data: dict, current_user: dict):
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


