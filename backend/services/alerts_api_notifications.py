"""Alerts notifications handlers.

Extraído de `routes/alerts.py`.
Do **not** overwrite services/alerts.py — use alerts_api_*.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db


def build_notifications_query(user: dict, *, unread_only: bool = False) -> dict:
    """Notificações de UM utilizador — e só dele.

    O eixo desta consulta estava errado (Lote 5, ponto 3): filtrava por
    VISIBILIDADE DE PROCESSO e isentava admin/CEO/diretor. Resultado: a
    gestão recebia tudo o que existia na colecção, um consultor via as
    notificações do mediador do mesmo processo, e `{"process_id": None}`
    mandava os avisos sem processo para toda a gente.

    O campo que diz o destinatário — `user_id` — existia e era ignorado.
    Hoje é o único critério: o cargo não decide visibilidade de dados
    pessoais, e o isolamento entre redes está acima da conveniência de um
    painel de sistema (decisão do dono).
    """
    user_id = str((user or {}).get("id") or "").strip()
    if not user_id:
        # Fail-closed: sem utilizador não há notificações de ninguém.
        return {"user_id": {"$in": []}}

    query: dict = {"user_id": user_id}
    if unread_only:
        query["read"] = False
    return query


async def run_get_notifications(unread_only: bool, user: dict):
    """Obter as notificações dirigidas ao utilizador autenticado."""
    query = build_notifications_query(user, unread_only=unread_only)

    notifications = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    # A contagem segue o MESMO âmbito: um sino com um número que não bate
    # certo com a lista é pior do que um sino sem número.
    total_unread = await db.notifications.count_documents(
        {**query, "read": False}
    )

    return {
        "notifications": notifications,
        "total": len(notifications),
        "unread": total_unread
    }


async def run_mark_notification_read(notification_id: str, user: dict):
    """Marcar como lida uma notificação DO PRÓPRIO (idempotente).

    Sem o utilizador no filtro, quem tivesse um id marcava a notificação
    de outra pessoa — uma escrita na linha de outrem. O caminho WebSocket
    (`mark_all_read`) já filtrava por `user_id`; este não.

    Devolve 404 (e não 403) quando a notificação é de outro: distinguir
    "não existe" de "não é tua" confirmaria a existência do id a quem não
    tem nada que ver com ela.
    """
    dono = {"user_id": str((user or {}).get("id") or "").strip()}
    if not dono["user_id"]:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    result = await db.notifications.update_one(
        {"id": notification_id, **dono},
        {"$set": {"read": True}}
    )

    if result.matched_count == 0:
        result = await db.notifications.update_one(
            {"_id": notification_id, **dono},
            {"$set": {"read": True}}
        )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    return {"success": True}
