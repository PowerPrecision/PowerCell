"""List / by-status / consultores lead endpoints.

Extraído de `routes/leads.py`.
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime, timezone

from database import db
from models.lead import LeadStatus


async def run_list_leads(
    user: dict,
    status: Optional[LeadStatus] = None,
    client_id: Optional[str] = None,
    consultor_id: Optional[str] = None,
):
    """
    Listar todos os leads de imóveis com filtros opcionais.

    Regras de visibilidade:
    - Admin/Director: Vê todos os leads
    - Consultor/Mediador: Só vê os seus leads
    """
    query = {}
    user_role = user.get("role", "")
    user_id = user.get("id")

    # Filtrar por utilizador se não for admin/director
    if user_role not in ["admin", "diretor"]:
        query["created_by_id"] = user_id
    elif consultor_id:
        query["created_by_id"] = consultor_id

    if status:
        query["status"] = status.value
    if client_id:
        query["client_id"] = client_id

    # Busca leads e exclui o _id do mongo
    leads = await db.property_leads.find(query, {"_id": 0}).to_list(length=500)

    # Enriquecer com nome do cliente (batch com $in — evita N+1)
    client_ids = list({lead["client_id"] for lead in leads if lead.get("client_id")})
    if client_ids:
        procs = await db.processes.find(
            {"id": {"$in": client_ids}},
            {"id": 1, "client_name": 1, "_id": 0}
        ).to_list(length=len(client_ids))
        name_by_id = {p["id"]: p.get("client_name") for p in procs}
        for lead in leads:
            cid = lead.get("client_id")
            if cid in name_by_id:
                lead["client_name"] = name_by_id[cid]

    return leads


async def run_get_leads_by_status(
    user: dict,
    consultor_id: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    """
    Obter leads agrupados por status (para o Kanban).
    Suporta filtros por consultor e por estado.

    Regras de visibilidade:
    - Admin/Director: Vê todos os leads (pode filtrar por consultor)
    - Consultor/Mediador: Só vê os seus leads (created_by_id = user_id)
    """
    query = {}
    user_role = user.get("role", "")
    user_id = user.get("id")

    # Filtrar por utilizador se não for admin/director
    if user_role not in ["admin", "diretor"]:
        # Consultor/Mediador só vê os seus leads
        query["created_by_id"] = user_id
    elif consultor_id:
        # Admin/Director pode filtrar por consultor específico
        query["created_by_id"] = consultor_id

    if status_filter and status_filter != "all":
        query["status"] = status_filter

    leads = await db.property_leads.find(query, {"_id": 0}).to_list(length=500)

    # Inicializar grupos
    grouped = {status.value: [] for status in LeadStatus}

    # Enriquecer nome do cliente (batch com $in — evita N+1)
    client_ids = list({lead["client_id"] for lead in leads if lead.get("client_id")})
    name_by_id = {}
    if client_ids:
        procs = await db.processes.find(
            {"id": {"$in": client_ids}},
            {"id": 1, "client_name": 1, "_id": 0}
        ).to_list(length=len(client_ids))
        name_by_id = {p["id"]: p.get("client_name") for p in procs}

    for lead in leads:
        # Enriquecer nome do cliente
        cid = lead.get("client_id")
        if cid in name_by_id:
            lead["client_name"] = name_by_id[cid]

        # Calcular dias desde criação
        if lead.get("created_at"):
            try:
                created = datetime.fromisoformat(lead["created_at"].replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - created).days
                lead["days_old"] = days_old
                lead["is_stale"] = days_old > 7 and lead.get("status") == LeadStatus.NOVO.value
            except:
                lead["days_old"] = 0
                lead["is_stale"] = False

        # Agrupar
        lead_status = lead.get("status", LeadStatus.NOVO.value)
        if lead_status in grouped:
            grouped[lead_status].append(lead)
        else:
            grouped[LeadStatus.NOVO.value].append(lead)

    return grouped


async def run_get_consultores_for_filter(user: dict):
    """
    Obter lista de consultores para os filtros do Kanban.
    Retorna utilizadores com role consultor, diretor ou admin.
    """
    from services.role_query import deep_role_in_filter
    consultores = await db.users.find(
        deep_role_in_filter(["consultor", "diretor", "admin", "administrativo"]),
        {"_id": 0, "id": 1, "name": 1, "email": 1}
    ).to_list(length=100)

    return consultores
