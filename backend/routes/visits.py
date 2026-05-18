"""
Rotas para Gestão de Visitas (Quadro de Visitas)
==================
Endpoints CRUD para visitas a imóveis, com agendamento, 
alteração de estado e filtros por consultor/imóvel/cliente.

ENDPOINTS:
- GET  /visits           → Lista visitas (filtros: status, consultor, imóvel, data)
- POST /visits           → Agendar nova visita
- GET  /visits/{id}      → Detalhe de visita
- PATCH /visits/{id}     → Actualizar visita (status, data, notas)
- DELETE /visits/{id}    → Cancelar visita (soft delete → status cancelada)
- GET  /visits/calendar  → Visitas em formato calendário (por mês)
"""
import uuid
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query

from database import db
from services.auth import get_current_user

router = APIRouter(prefix="/visits", tags=["Visits"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_visits(
    status: Optional[str] = Query(None, description="Filtrar por estado: agendada, concluida, cancelada"),
    consultor_id: Optional[str] = Query(None, description="Filtrar por consultor"),
    property_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    client_id: Optional[str] = Query(None, description="Filtrar por cliente (process_id)"),
    date_from: Optional[str] = Query(None, description="Data início (ISO)"),
    date_to: Optional[str] = Query(None, description="Data fim (ISO)"),
    user: dict = Depends(get_current_user)
):
    """
    Lista visitas com filtros opcionais.
    Consultores só vêem as suas visitas; admins/ceo/diretores vêem todas.
    """
    query = {}

    # Filtros
    if status:
        valid_statuses = ["solicitada", "agendada", "concluida", "cancelada"]
        if status in valid_statuses:
            query["status"] = status
        else:
            query["status"] = status

    if consultor_id:
        query["consultor_id"] = consultor_id
    if property_id:
        query["property_id"] = property_id
    if client_id:
        query["client_id"] = client_id

    # Filtro por data
    if date_from or date_to:
        date_query = {}
        if date_from:
            date_query["$gte"] = date_from
        if date_to:
            date_query["$lte"] = date_to
        query["scheduled_date"] = date_query

    # RBAC: consultores e intermediários só vêem as suas visitas
    user_role = (user.get("role") or "").lower()
    if user_role in ["consultor", "intermediario"]:
        query["$or"] = [
            {"consultor_id": user.get("id")},
            {"consultor_ids": user.get("id")},
        ]

    visits = await db.visits.find(query, {"_id": 0}).sort("scheduled_date", 1).to_list(200)

    # Enriquecer com nomes (denormalizados, mas confirmamos)
    for visit in visits:
        # Garantir que temos os nomes
        if not visit.get("property_title") and visit.get("property_id"):
            prop = await db.properties.find_one({"id": visit["property_id"]}, {"title": 1, "photos": 1})
            if prop:
                visit["property_title"] = prop.get("title", "")
                visit["property_photo"] = (prop.get("photos") or [None])[0]

    return visits


@router.post("")
async def create_visit(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Agendar uma nova visita a um imóvel.

    Body:
    - property_id: ID do imóvel (obrigatório)
    - client_id: ID do processo/cliente (obrigatório)
    - scheduled_date: Data/hora da visita ISO (obrigatório)
    - consultor_id: ID do consultor (opcional, padrão = user actual)
    - notes: Notas (opcional)
    """
    property_id = data.get("property_id")
    client_id = data.get("client_id")
    scheduled_date = data.get("scheduled_date")
    consultor_id = data.get("consultor_id") or user.get("id")
    notes = data.get("notes", "")

    if not property_id:
        raise HTTPException(status_code=400, detail="property_id é obrigatório")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id é obrigatório")
    if not scheduled_date:
        raise HTTPException(status_code=400, detail="scheduled_date é obrigatório")

    # Verificar imóvel
    prop = await db.properties.find_one({"id": property_id}, {"title": 1, "photos": 1, "address": 1})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")

    # Buscar dados do cliente (processo)
    process = await db.processes.find_one({"id": client_id}, {"client_name": 1, "client_email": 1, "client_phone": 1})
    client_name = process.get("client_name", "") if process else ""
    client_email = process.get("client_email", "") if process else ""
    client_phone = process.get("client_phone", "") if process else ""

    # Buscar dados do consultor
    consultor = await db.users.find_one({"id": consultor_id}, {"name": 1, "email": 1, "phone": 1})
    consultor_name = consultor.get("name", "") if consultor else user.get("name", "")

    now = datetime.now(timezone.utc).isoformat()
    visit_id = str(uuid.uuid4())

    visit_doc = {
        "id": visit_id,
        "property_id": property_id,
        "property_title": prop.get("title", ""),
        "property_photo": (prop.get("photos") or [None])[0],
        "property_address": prop.get("address", {}),
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "consultor_id": consultor_id,
        "consultor_name": consultor_name,
        "scheduled_date": scheduled_date,
        "status": "agendada",
        "notes": notes,
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("id"),
        "company_id": user.get("company_id"),
    }

    await db.visits.insert_one(visit_doc)

    # Incrementar visit_count no imóvel
    await db.properties.update_one(
        {"id": property_id},
        {"$inc": {"visit_count": 1}}
    )

    # Registar no histórico do processo
    try:
        from services.history import log_history
        await log_history(
            client_id,
            user=user,
            action="VISIT_SCHEDULED",
            field="visita",
            old_value=None,
            new_value=f"Visita agendada a '{prop.get('title', '')}' para {scheduled_date}"
        )
    except Exception as e:
        logger.warning(f"[VISITS] Erro ao registar histórico: {e}")

    logger.info(f"[VISITS] Visita agendada: {visit_id} — Imóvel {property_id}, Cliente {client_name}")

    visit_doc.pop("_id", None)
    return visit_doc


@router.get("/kanban")
async def get_visits_kanban(
    consultor_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    Retorna visitas organizadas por estado para o Quadro de Visitas.
    Colunas: agendada, concluida, cancelada
    """
    query = {}

    # RBAC
    user_role = (user.get("role") or "").lower()
    if user_role in ["consultor", "intermediario"]:
        query["$or"] = [
            {"consultor_id": user.get("id")},
            {"consultor_ids": user.get("id")},
        ]
    elif consultor_id:
        query["consultor_id"] = consultor_id

    visits = await db.visits.find(query, {"_id": 0}).sort("scheduled_date", 1).to_list(200)

    solicitadas = [v for v in visits if v.get("status") == "solicitada"]
    agendadas = [v for v in visits if v.get("status") == "agendada"]
    concluidas = [v for v in visits if v.get("status") == "concluida"]
    canceladas = [v for v in visits if v.get("status") == "cancelada"]

    return {
        "solicitadas": solicitadas,
        "agendadas": agendadas,
        "concluidas": concluidas,
        "canceladas": canceladas,
        "total": len(visits),
    }


@router.get("/{visit_id}")
async def get_visit(
    visit_id: str,
    user: dict = Depends(get_current_user)
):
    """Obtém detalhe de uma visita."""
    visit = await db.visits.find_one({"id": visit_id}, {"_id": 0})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")
    return visit


@router.patch("/{visit_id}")
async def update_visit(
    visit_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Actualizar visita (status, data, notas, etc.)

    Status válidos: agendada, concluida, cancelada
    """
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"updated_at": now}

    # Campos actualizáveis
    if "status" in data:
        new_status = data["status"]
        if new_status not in ["agendada", "concluida", "cancelada", "solicitada"]:
            raise HTTPException(status_code=400, detail="Status inválido. Use: agendada, concluida, cancelada")
        update_fields["status"] = new_status

    if "scheduled_date" in data:
        update_fields["scheduled_date"] = data["scheduled_date"]

    if "notes" in data:
        update_fields["notes"] = data["notes"]

    if "consultor_id" in data:
        consultor = await db.users.find_one({"id": data["consultor_id"]}, {"name": 1})
        update_fields["consultor_id"] = data["consultor_id"]
        update_fields["consultor_name"] = consultor.get("name", "") if consultor else ""

    await db.visits.update_one(
        {"id": visit_id},
        {"$set": update_fields}
    )

    # Registar no histórico
    if "status" in data and data["status"] != visit.get("status"):
        try:
            from services.history import log_history
            status_labels = {"solicitada": "Solicitada", "agendada": "Agendada", "concluida": "Concluída", "cancelada": "Cancelada"}
            await log_history(
                visit.get("client_id", ""),
                user=user,
                action="VISIT_STATUS_CHANGED",
                field="visita",
                old_value=status_labels.get(visit.get("status"), visit.get("status")),
                new_value=status_labels.get(data["status"], data["status"])
            )
        except Exception as e:
            logger.warning(f"[VISITS] Erro ao registar histórico: {e}")

    updated = await db.visits.find_one({"id": visit_id}, {"_id": 0})
    return updated


@router.delete("/{visit_id}")
async def cancel_visit(
    visit_id: str,
    user: dict = Depends(get_current_user)
):
    """Cancelar visita (soft delete — muda status para 'cancelada')."""
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    await db.visits.update_one(
        {"id": visit_id},
        {"$set": {"status": "cancelada", "updated_at": now, "cancelled_at": now, "cancelled_by": user.get("id")}}
    )

    return {"success": True, "message": "Visita cancelada"}
