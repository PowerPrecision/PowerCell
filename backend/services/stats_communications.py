"""Communications feed for executive dashboards.

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

import logging

from database import db
from models.auth import UserRole

logger = logging.getLogger(__name__)

async def run_get_communications_feed(user: dict):
    """
    Feed de comunicações para os Dashboards Executivos.

    Retorna dois arrays de dados:
    a) Avisos do Portal: Últimas mensagens submetidas por clientes no portal
       onde read_by_staff é False.
    b) Emails Pendentes: Últimos emails recebidos com is_read a False.

    Filtrado pelo role do utilizador:
    - Admin/CEO/Administrativo/Diretor: vê tudo
    - Consultores/Intermediários: vê apenas dos seus processos
    - Indexação: vê apenas dos seus processos
    - Clientes: não vê nada (dados internos)

    NOTA: TTL curto (5 min) porque comunicações são time-sensitive.
    """
    import logging
    _logger = logging.getLogger(__name__)

    role = user["role"]
    user_id = user["id"]

    # Clientes não têm acesso ao feed de comunicações internas
    if role == UserRole.CLIENTE:
        return {"portal_messages": [], "unread_emails": [], "portal_unread_count": 0, "email_unread_count": 0}

    # ── Determinar process_ids do utilizador (para filtragem por role) ──
    process_ids = None  # None = sem filtro (vê tudo)

    if role not in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # Consultores/Intermediários/Indexação: apenas os seus processos
        or_conditions = [
            {"assigned_consultor_id": user_id},
            {"consultor_id": user_id},
            {"assigned_mediador_id": user_id},
            {"intermediario_id": user_id},
        ]
        if role == UserRole.INDEXACAO:
            or_conditions = [{"assigned_indexacao_id": user_id}]

        my_processes = await db.processes.find(
            {"$or": or_conditions, "is_deleted": {"$ne": True}},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        process_ids = [p["id"] for p in my_processes]

    # ── Portal Messages (não lidas pelo staff) ──
    portal_query = {"read_by_staff": False}
    if process_ids is not None:
        portal_query["process_id"] = {"$in": process_ids}

    portal_cursor = db.portal_messages.find(
        portal_query,
        {"_id": 0}
    ).sort("created_at", -1).limit(15)

    portal_messages = []
    async for msg in portal_cursor:
        # Enriquecer com nome do processo/cliente
        process_info = await db.processes.find_one(
            {"id": msg.get("process_id")},
            {"client_name": 1, "process_number": 1, "_id": 0}
        )
        portal_messages.append({
            "id": msg.get("id"),
            "process_id": msg.get("process_id"),
            "sender_name": msg.get("sender_name", "Cliente"),
            "content": (msg.get("content") or "")[:150],
            "created_at": msg.get("created_at"),
            "client_name": process_info.get("client_name", "") if process_info else "",
            "process_number": process_info.get("process_number") if process_info else None,
        })

    # ── Emails Pendentes (não lidos) ──
    email_query = {"is_read": False}
    if process_ids is not None:
        email_query["process_id"] = {"$in": process_ids}

    # A coleção de emails pode variar — verificar se existe 'emails'
    email_cursor = db.emails.find(
        email_query,
        {"_id": 0}
    ).sort("received_at", -1).limit(15)

    unread_emails = []
    async for email in email_cursor:
        # Enriquecer com nome do processo/cliente
        process_info = None
        if email.get("process_id"):
            process_info = await db.processes.find_one(
                {"id": email["process_id"]},
                {"client_name": 1, "process_number": 1, "_id": 0}
            )
        unread_emails.append({
            "id": email.get("id"),
            "process_id": email.get("process_id"),
            "subject": email.get("subject", "(Sem assunto)"),
            "from_address": email.get("from_address", email.get("from", "")),
            "received_at": email.get("received_at", email.get("created_at")),
            "client_name": process_info.get("client_name", "") if process_info else "",
            "process_number": process_info.get("process_number") if process_info else None,
        })

    # Contagens totais (para os KPI cards)
    portal_unread_count = await db.portal_messages.count_documents(portal_query)
    email_unread_count = await db.emails.count_documents(email_query)

    return {
        "portal_messages": portal_messages,
        "unread_emails": unread_emails,
        "portal_unread_count": portal_unread_count,
        "email_unread_count": email_unread_count,
    }

