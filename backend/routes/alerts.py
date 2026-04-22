"""
====================================================================
ROTAS DE ALERTAS E NOTIFICAÇÕES - CREDITOIMO
====================================================================
Endpoints para gestão de alertas e notificações do sistema.

Autor: PowerCell Development Team
====================================================================
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.auth import UserRole
from services.auth import get_current_user
from services.alerts import (
    get_process_alerts,
    check_age_alert,
    check_pre_approval_countdown,
    check_document_expiry_alerts,
    check_property_documents,
    create_deed_reminder,
    ALERT_TYPES
)


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/process/{process_id}")
async def get_alerts_for_process(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter todos os alertas para um processo específico.
    
    Retorna:
    - Alerta de idade (< 35 anos)
    - Countdown de pré-aprovação (90 dias)
    - Alertas de documentos a expirar
    - Verificação de documentos do imóvel
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    alerts = await get_process_alerts(process)
    
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "status": process.get("status"),
        "alerts": alerts,
        "total_alerts": len(alerts),
        "has_critical": any(a.get("priority") == "critical" for a in alerts),
        "has_high": any(a.get("priority") == "high" for a in alerts)
    }


@router.get("/age-check/{process_id}")
async def check_age_eligibility(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Verificar se o cliente é elegível para apoio ao estado (< 35 anos).
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return check_age_alert(process)


@router.get("/pre-approval/{process_id}")
async def get_pre_approval_countdown(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter o countdown de 90 dias da pré-aprovação.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return await check_pre_approval_countdown(process)


@router.get("/documents/{process_id}")
async def get_document_alerts(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter alertas de documentos a expirar (15 dias).
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    doc_alerts = await check_document_expiry_alerts(process_id)
    
    return {
        "process_id": process_id,
        "alerts": doc_alerts,
        "total": len(doc_alerts)
    }


@router.get("/property-docs/{process_id}")
async def check_property_docs(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Verificar se os documentos do imóvel estão completos.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return await check_property_documents(process)


@router.post("/deed-reminder/{process_id}")
async def create_deed_reminder_endpoint(
    process_id: str,
    deed_date: str,
    user: dict = Depends(get_current_user)
):
    """
    Criar um lembrete de escritura 15 dias antes da data.
    
    Args:
        deed_date: Data da escritura (YYYY-MM-DD)
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    deadline_id = await create_deed_reminder(process, deed_date, user)
    
    if deadline_id:
        return {
            "success": True,
            "deadline_id": deadline_id,
            "message": "Lembrete de escritura criado com sucesso"
        }
    else:
        return {
            "success": False,
            "message": "Não foi possível criar o lembrete (data pode já ter passado)"
        }


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    user: dict = Depends(get_current_user)
):
    """
    Obter notificações do sistema.
    
    Regras de visibilidade:
    - Admin, CEO, Diretor: vêem TODAS as notificações (incluindo novos registos)
    - Outros (incluindo Indexação): vêem apenas notificações dos seus processos
    """
    query = {}
    
    if unread_only:
        query["read"] = False
    
    # Apenas Admin, CEO e Diretor vêem todas as notificações
    if user["role"] not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
        # Outros utilizadores vêem apenas notificações dos seus processos
        # E NÃO vêem notificações de novos registos
        or_conditions = [
            {"assigned_consultor_id": user["id"]},
            {"consultor_id": user["id"]},
            {"assigned_mediador_id": user["id"]},
            {"intermediario_id": user["id"]},
            {"assigned_indexacao_id": user["id"]}  # Indexação vê processos atribuídos a ele
        ]
        
        processes = await db.processes.find({
            "$or": or_conditions
        }, {"id": 1, "_id": 0}).to_list(1000)
        process_ids = [p["id"] for p in processes]
        
        # Excluir notificações de novos registos para utilizadores não-admin
        query["$and"] = [
            {"$or": [
                {"process_id": {"$in": process_ids}},
                {"process_id": None}  # Notificações sem processo específico
            ]},
            {"type": {"$ne": "new_registration"}}  # Excluir novos registos
        ]
    
    notifications = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    # Contar total de não lidas a nível da BD (não limitado ao batch de 100)
    unread_query = {**query, "read": False}
    total_unread = await db.notifications.count_documents(unread_query)
    
    return {
        "notifications": notifications,
        "total": len(notifications),
        "unread": total_unread
    }


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Marcar notificação como lida.
    """
    result = await db.notifications.update_one(
        {"id": notification_id},
        {"$set": {"read": True}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    
    return {"success": True}
