"""
Rotas para Gestão de Visitas (Quadro de Visitas)
==================
Endpoints CRUD para visitas a imóveis, com agendamento,
alteração de estado e filtros por consultor/imóvel/cliente.

v2 — Integração com Portal, Scraper e Calendário:
- POST /visits suporta URL de imóvel (invoca scraper em background)
- PATCH /visits/{id} sincroniza com Calendário (deadlines) e Portal
- Visitas do portal incluem process_id explícito
- Status 'recusada' adicionado (além de cancelada)

ENDPOINTS:
- GET  /visits           → Lista visitas (filtros: status, consultor, imóvel, data, process_id)
- POST /visits           → Criar nova visita (com scraper opcional)
- GET  /visits/kanban    → Visitas organizadas por estado
- GET  /visits/{id}      → Detalhe de visita
- PATCH /visits/{id}     → Actualizar visita (status, data, notas) + sync calendário/portal
- DELETE /visits/{id}    → Cancelar visita (soft delete → status cancelada)
"""
import uuid
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query

from database import db
from services.auth import get_current_user

router = APIRouter(prefix="/visits", tags=["Visits"])
logger = logging.getLogger(__name__)


# ================================================================
# HELPERS — Sincronização com Calendário e Portal
# ================================================================

async def _create_calendar_event_for_visit(visit: dict):
    """
    Cria um registo na coleção de deadlines (calendário do CRM)
    quando uma visita transita para 'agendada'.

    Título: 'Visita Imóvel: [Nome do Imóvel]'
    Associado ao consultor e ao processo.
    """
    try:
        deadline_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        property_name = visit.get("property_title") or "Imóvel"
        scheduled_date = visit.get("scheduled_date")

        consultor_id = visit.get("consultor_id")
        process_id = visit.get("client_id")  # client_id = process_id

        assigned_users = [uid for uid in [consultor_id] if uid]

        deadline_doc = {
            "id": deadline_id,
            "process_id": process_id,
            "visit_id": visit.get("id"),  # Referência cruzada
            "title": f"Visita Imóvel: {property_name}",
            "description": (
                f"Visita agendada a '{property_name}'"
                f"{f' — {visit.get(\"client_name\", \"\")}' if visit.get('client_name') else ''}"
                f"\nNotas: {visit.get('notes', '—')}"
            ),
            "due_date": scheduled_date or now,
            "priority": "alta",
            "completed": False,
            "created_by": consultor_id or "system",
            "created_at": now,
            "assigned_user_ids": assigned_users,
            "source": "visit_schedule",
            "assigned_consultor_id": consultor_id,
            "assigned_mediador_id": None,
        }

        await db.deadlines.insert_one(deadline_doc)
        logger.info(f"[VISITS] Evento de calendário criado: {deadline_id} para visita {visit.get('id')}")
        return deadline_id

    except Exception as e:
        logger.warning(f"[VISITS] Erro ao criar evento de calendário: {e}")
        return None


async def _remove_calendar_event_for_visit(visit_id: str):
    """
    Remove o evento de calendário associado a uma visita
    quando é cancelada ou recusada.
    """
    try:
        result = await db.deadlines.delete_many({"visit_id": visit_id})
        if result.deleted_count > 0:
            logger.info(f"[VISITS] {result.deleted_count} evento(s) de calendário removido(s) para visita {visit_id}")
    except Exception as e:
        logger.warning(f"[VISITS] Erro ao remover evento de calendário: {e}")


async def _update_portal_visit_status(visit: dict, new_status: str, scheduled_date: str = None):
    """
    Atualiza o estado da visita no Portal do Cliente.

    Quando a visita é agendada, define a data oficial.
    Quando é recusada/cancelada, atualiza o estado no portal.
    """
    try:
        process_id = visit.get("client_id")  # client_id = process_id
        visit_id = visit.get("id")

        update_fields = {
            "portal_status": new_status,
            "portal_updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if new_status == "agendada" and scheduled_date:
            update_fields["portal_scheduled_date"] = scheduled_date

        if new_status in ("cancelada", "recusada"):
            update_fields["portal_cancelled_at"] = datetime.now(timezone.utc).isoformat()
            update_fields.pop("portal_scheduled_date", None)

        await db.visits.update_one(
            {"id": visit_id},
            {"$set": update_fields}
        )

        # Notificar via WebSocket para a sala do processo
        try:
            from services.websocket_manager import manager, WSEventType, create_ws_message
            ws_data = {
                "visit_id": visit_id,
                "status": new_status,
                "property_title": visit.get("property_title", "Imóvel"),
            }
            if scheduled_date:
                ws_data["scheduled_date"] = scheduled_date

            ws_message = create_ws_message(WSEventType.PORTAL_MESSAGE, {
                "type": "visit_status_update",
                **ws_data,
            })
            await manager.broadcast_to_room(f"process_{process_id}", ws_message)
        except Exception as ws_err:
            logger.debug(f"[VISITS] Erro ao notificar portal via WS: {ws_err}")

        logger.info(f"[VISITS] Portal atualizado: visita {visit_id} → {new_status}")

    except Exception as e:
        logger.warning(f"[VISITS] Erro ao atualizar portal: {e}")


async def _run_scraper_for_visit(visit_id: str, url: str):
    """
    Invoca o scraper em background para extrair dados do imóvel
    a partir de um URL (Idealista/Imovirtual).

    Atualiza o documento da visita com os dados extraídos.
    """
    try:
        from services.property_scraper import extract_property_data
        scraped_result = await extract_property_data(url)

        scraped_data = {
            "title": scraped_result.title,
            "price": scraped_result.price,
            "location": scraped_result.location,
            "typology": scraped_result.typology,
            "area": scraped_result.area,
            "photo_url": scraped_result.photo_url,
            "source": scraped_result.source,
            "url": url,
            "consultant": {
                "name": scraped_result.consultant.name if scraped_result.consultant else None,
                "phone": scraped_result.consultant.phone if scraped_result.consultant else None,
                "email": scraped_result.consultant.email if scraped_result.consultant else None,
                "agency_name": scraped_result.consultant.agency_name if scraped_result.consultant else None,
            } if scraped_result.consultant else None,
        }

        # Atualizar visita com dados do scraper
        update_fields = {
            "scraped_data": scraped_data,
            "scraped_url": url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Auto-popular campos da visita com dados extraídos
        if scraped_data.get("title") and not scraped_result.source == "error":
            update_fields["property_title"] = scraped_data["title"]

        if scraped_data.get("price"):
            update_fields["scraped_price"] = scraped_data["price"]

        if scraped_data.get("photo_url"):
            update_fields["property_photo"] = scraped_data["photo_url"]

        if scraped_data.get("location"):
            update_fields["property_address"] = {
                "municipality": scraped_data["location"],
                "district": "",
            }

        if scraped_data.get("typology"):
            update_fields["scraped_typology"] = scraped_data["typology"]

        await db.visits.update_one(
            {"id": visit_id},
            {"$set": update_fields}
        )

        logger.info(f"[VISITS] Scraper completado para visita {visit_id}: {scraped_data.get('title', 'sem título')}")

    except Exception as e:
        logger.warning(f"[VISITS] Erro no scraper para visita {visit_id}: {e}")
        # Marcar erro no scraper
        try:
            await db.visits.update_one(
                {"id": visit_id},
                {"$set": {
                    "scraper_error": str(e),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
        except Exception:
            pass


# ================================================================
# ENDPOINTS
# ================================================================

@router.get("")
async def list_visits(
    status: Optional[str] = Query(None, description="Filtrar por estado: agendada, concluida, cancelada"),
    consultor_id: Optional[str] = Query(None, description="Filtrar por consultor"),
    property_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    client_id: Optional[str] = Query(None, description="Filtrar por cliente (process_id)"),
    process_id: Optional[str] = Query(None, description="Filtrar por process_id"),
    date_from: Optional[str] = Query(None, description="Data início (ISO)"),
    date_to: Optional[str] = Query(None, description="Data fim (ISO)"),
    user: dict = Depends(get_current_user)
):
    """
    Lista visitas com filtros opcionais.
    Consultores só vêem as suas visitas; admins/ceo/diretores vêem todas.
    Suporta filtro por process_id para a aba de Visitas no ProcessDetailsModal.
    """
    query = {}

    # Filtros
    if status:
        query["status"] = status

    if consultor_id:
        query["consultor_id"] = consultor_id
    if property_id:
        query["property_id"] = property_id
    if client_id:
        query["client_id"] = client_id
    if process_id:
        # Suportar ambos: client_id (legacy) e process_id (novo)
        query["$or"] = [
            {"client_id": process_id},
            {"process_id": process_id},
        ]

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
        rbac_filter = [
            {"consultor_id": user.get("id")},
            {"consultor_ids": user.get("id")},
        ]
        # Se já tem $or (do process_id), combinar com $and
        if "$or" in query:
            or_clause = query.pop("$or")
            query["$and"] = [
                {"$or": or_clause},
                {"$or": rbac_filter},
            ]
        else:
            query["$or"] = rbac_filter

    visits = await db.visits.find(query, {"_id": 0, "scraped_data.raw_data": 0}).sort("scheduled_date", 1).to_list(200)

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
    Criar uma nova visita a um imóvel.

    v2: Suporta URL do imóvel (Idealista/Imovirtual) que invoca o scraper
    em background para auto-popular os dados da visita.

    Body:
    - property_id: ID do imóvel (obrigatório se não houver property_url)
    - client_id: ID do processo/cliente (obrigatório)
    - scheduled_date: Data/hora da visita ISO (obrigatório)
    - consultor_id: ID do consultor (opcional, padrão = user actual)
    - notes: Notas (opcional)
    - property_url: URL do imóvel para scraper (opcional — Idealista/Imovirtual)
    """
    property_id = data.get("property_id")
    client_id = data.get("client_id")
    scheduled_date = data.get("scheduled_date")
    consultor_id = data.get("consultor_id") or user.get("id")
    notes = data.get("notes", "")
    property_url = data.get("property_url", "").strip()

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id é obrigatório")
    if not property_id and not property_url:
        raise HTTPException(status_code=400, detail="property_id ou property_url é obrigatório")
    if not scheduled_date:
        raise HTTPException(status_code=400, detail="scheduled_date é obrigatório")

    # Buscar processo ativo para este client_id e obter o process_id
    process = await db.processes.find_one({"id": client_id}, {
        "client_name": 1, "client_email": 1, "client_phone": 1,
        "status": 1, "assigned_consultor_id": 1,
    })
    client_name = process.get("client_name", "") if process else ""
    client_email = process.get("client_email", "") if process else ""
    client_phone = process.get("client_phone", "") if process else ""
    process_id = client_id  # Na arquitetura actual, client_id = process_id

    # Buscar dados do imóvel (se property_id fornecido)
    prop_data = {}
    if property_id:
        prop = await db.properties.find_one({"id": property_id}, {"title": 1, "photos": 1, "address": 1})
        if not prop:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        prop_data = {
            "property_title": prop.get("title", ""),
            "property_photo": (prop.get("photos") or [None])[0],
            "property_address": prop.get("address", {}),
        }

    # Buscar dados do consultor
    consultor = await db.users.find_one({"id": consultor_id}, {"name": 1, "email": 1, "phone": 1})
    consultor_name = consultor.get("name", "") if consultor else user.get("name", "")

    now = datetime.now(timezone.utc).isoformat()
    visit_id = str(uuid.uuid4())

    visit_doc = {
        "id": visit_id,
        "property_id": property_id,
        **prop_data,
        "client_id": client_id,
        "process_id": process_id,  # Explícito para queries
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

    # Se tem property_url, adicionar ao documento e lançar scraper em background
    if property_url:
        visit_doc["scraped_url"] = property_url
        visit_doc["scraper_status"] = "pending"

        # Se não temos property_id, é uma visita com imóvel externo
        if not property_id:
            visit_doc["property_id"] = None
            # Usar URL como fallback para o título
            visit_doc.setdefault("property_title", f"Imóvel de {property_url.split('//')[-1][:50]}...")

    await db.visits.insert_one(visit_doc)

    # Incrementar visit_count no imóvel (se existir)
    if property_id:
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
            action="VISIT_CREATED",
            field="visita",
            old_value=None,
            new_value=f"Visita criada a '{visit_doc.get('property_title', '')}' para {scheduled_date}"
        )
    except Exception as e:
        logger.warning(f"[VISITS] Erro ao registar histórico: {e}")

    # ── Criar evento no calendário (visita já nasce agendada) ──
    await _create_calendar_event_for_visit(visit_doc)

    # ── Atualizar portal ──
    await _update_portal_visit_status(visit_doc, "agendada", scheduled_date)

    # ── Lançar scraper em background se URL fornecida ──
    if property_url:
        asyncio.create_task(_run_scraper_for_visit(visit_id, property_url))
        logger.info(f"[VISITS] Scraper lançado em background para visita {visit_id}")

    logger.info(f"[VISITS] Visita criada: {visit_id} — Imóvel {property_id or property_url}, Cliente {client_name}")

    visit_doc.pop("_id", None)
    return visit_doc


@router.get("/kanban")
async def get_visits_kanban(
    consultor_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    Retorna visitas organizadas por estado para o Quadro de Visitas.
    Colunas: solicitada, agendada, concluida, cancelada
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

    visits = await db.visits.find(query, {"_id": 0, "scraped_data.raw_data": 0}).sort("scheduled_date", 1).to_list(200)

    solicitadas = [v for v in visits if v.get("status") == "solicitada"]
    agendadas = [v for v in visits if v.get("status") == "agendada"]
    concluidas = [v for v in visits if v.get("status") == "concluida"]
    canceladas = [v for v in visits if v.get("status") in ("cancelada", "recusada")]

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
    visit = await db.visits.find_one({"id": visit_id}, {"_id": 0, "scraped_data.raw_data": 0})
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

    v2 — Sincronização com Calendário e Portal:
    - Status → 'agendada': Cria evento no calendário + atualiza portal
    - Status → 'cancelada'/'recusada': Remove evento do calendário + atualiza portal
    - scheduled_date alterado: Atualiza evento do calendário
    """
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Visita não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"updated_at": now}

    old_status = visit.get("status")
    new_status = data.get("status")

    # Campos actualizáveis
    if "status" in data:
        if new_status not in ["agendada", "concluida", "cancelada", "solicitada", "recusada"]:
            raise HTTPException(status_code=400, detail="Status inválido. Use: agendada, concluida, cancelada, recusada")
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

    # ── Sincronização com Calendário e Portal ──
    if new_status and new_status != old_status:
        # Status → 'agendada': Criar evento no calendário + atualizar portal
        if new_status == "agendada":
            scheduled_date = data.get("scheduled_date") or visit.get("scheduled_date")

            # Atualizar consultor na visita se fornecido
            updated_visit = {**visit, **update_fields}

            # Criar evento no calendário
            await _create_calendar_event_for_visit(updated_visit)

            # Atualizar portal do cliente
            await _update_portal_visit_status(visit, "agendada", scheduled_date)

        # Status → 'cancelada' ou 'recusada': Remover evento do calendário + atualizar portal
        elif new_status in ("cancelada", "recusada"):
            await _remove_calendar_event_for_visit(visit_id)
            await _update_portal_visit_status(visit, new_status)

            # Notificar cliente sobre cancelamento/recusa
            try:
                from services.notification_service import send_notification_with_preference_check
                client_email = visit.get("client_email")
                if client_email:
                    status_text = "cancelada" if new_status == "cancelada" else "recusada"
                    await send_notification_with_preference_check(
                        client_email,
                        f"Visita {status_text.capitalize()}",
                        f"A sua visita a '{visit.get('property_title', 'Imóvel')}' foi {status_text}. "
                        f"Contacte o seu consultor para mais informações.",
                        notification_type="visit_update",
                    )
            except Exception as e:
                logger.warning(f"[VISITS] Erro ao notificar cliente sobre {new_status}: {e}")

        # Status → 'concluida': Marcar evento como completo
        elif new_status == "concluida":
            try:
                await db.deadlines.update_many(
                    {"visit_id": visit_id},
                    {"$set": {"completed": True, "completed_at": now}}
                )
            except Exception as e:
                logger.warning(f"[VISITS] Erro ao marcar evento como completo: {e}")

            await _update_portal_visit_status(visit, "concluida")

    # Se scheduled_date foi alterado sem mudança de status, atualizar evento no calendário
    if "scheduled_date" in data and (not new_status or new_status == old_status):
        try:
            await db.deadlines.update_many(
                {"visit_id": visit_id},
                {"$set": {"due_date": data["scheduled_date"]}}
            )
        except Exception as e:
            logger.warning(f"[VISITS] Erro ao atualizar data do evento: {e}")

    # Registar no histórico
    if new_status and new_status != old_status:
        try:
            from services.history import log_history
            status_labels = {
                "solicitada": "Solicitada", "agendada": "Agendada",
                "concluida": "Concluída", "cancelada": "Cancelada", "recusada": "Recusada",
            }
            await log_history(
                visit.get("client_id", ""),
                user=user,
                action="VISIT_STATUS_CHANGED",
                field="visita",
                old_value=status_labels.get(old_status, old_status),
                new_value=status_labels.get(new_status, new_status)
            )
        except Exception as e:
            logger.warning(f"[VISITS] Erro ao registar histórico: {e}")

    updated = await db.visits.find_one({"id": visit_id}, {"_id": 0, "scraped_data.raw_data": 0})
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

    # Remover evento do calendário
    await _remove_calendar_event_for_visit(visit_id)

    # Atualizar portal
    await _update_portal_visit_status(visit, "cancelada")

    return {"success": True, "message": "Visita cancelada"}
