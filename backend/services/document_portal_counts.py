"""Contagem de ficheiros por pedido do Portal (expected_count vs uploaded_count).

BUGFIX (E2E — lógica de quantidade no Portal do Cliente, Set 2026): quando
um pedido pedia N ficheiros (ex.: "3 Recibos de Vencimento"), o primeiro
upload marcava logo o pedido como RECEIVED (concluído) — o cliente carregava
1 de 3 e o pedido dava-se por satisfeito, desbloqueando prematuramente o
auto-avanço do processo e o email de "documentação completa".

Regra canónica a partir deste módulo (usada pelo upload do cliente em
`portal_upload_ops.py` e pelo fulfil de uploads da equipa em
`document_portal_fulfill.py`):

    Um pedido portal (REQUESTED/PENDING) só passa a completed/RECEIVED
    quando o número de ficheiros carregados (uploaded_count =
    len(attached_files)) for >= à quantidade pedida (expected_count).

Origem do expected_count:
- Pedidos novos: item da checklist SystemConfig (`mandatory_documents` /
  `mandatory_checklist` / `mandatory_checklist_optional`) com campo
  opcional `quantity` (int >= 1; default 1) — gravado como
  `expected_count` no pedido no momento da geração.
- Pedidos legados sem `expected_count`: default 1 (comportamento anterior
  preservado — nenhum pedido existente regride).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

# Status que representam o pedido concluído (recebido por inteiro)
_COMPLETED_PORTAL_STATUSES = ("RECEIVED", "received")


def parse_expected_count(source: Optional[dict]) -> int:
    """
    Extrai a quantidade esperada de um item/pedido (>= 1, default 1).

    Aceita `expected_count` (campo do pedido) ou `quantity` (item da
    checklist SystemConfig); valores inválidos/negativos/zero degradam
    para 1 — nunca bloqueiam o fluxo.
    """
    if not isinstance(source, dict):
        return 1
    raw = source.get("expected_count", source.get("quantity"))
    if raw is None:
        return 1
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1
    return value if value >= 1 else 1


def is_portal_request_completed(doc: Optional[dict]) -> bool:
    """True se o pedido existe e já está concluído (RECEIVED)."""
    if not doc:
        return False
    return doc.get("status") in _COMPLETED_PORTAL_STATUSES


def describe_request_progress(doc: dict) -> str:
    """Resumo legível para logs (ex.: '1/3')."""
    expected = parse_expected_count(doc)
    uploaded = len(doc.get("attached_files") or [])
    return f"{uploaded}/{expected}"


async def apply_portal_request_upload(
    match_query: dict,
    *,
    set_fields: dict,
    file_entry: dict,
    now: str,
    completed_status: str = "RECEIVED",
) -> dict[str, Any]:
    """
    Anexa um ficheiro a um pedido portal e decide o status final pela contagem.

    Passos (tolerantes a concorrência — o $push é atómico no Mongo):
    1. `$push` do file_entry para `attached_files` + `$set` dos campos
       neutros (filename, s3_path, uploaded_at, ... — SEM status).
    2. Re-lê o pedido actualizado e conta `len(attached_files)`.
    3. Se uploaded_count >= expected_count → `$set status=completed_status`
       (+ uploaded_count/updated_at); senão mantém o status actual
       (REQUESTED/PENDING — o pedido continua pendente no Portal) e grava
       apenas o progresso (uploaded_count).

    Args:
        match_query: filtro Mongo do pedido (id + process_id/client_id +
            status pendente).
        set_fields: campos a $set (neutros — o caller não deve incluir
            `status`, é decidido aqui pela contagem).
        file_entry: entrada de ficheiro (anexada via $push).
        now: timestamp ISO para updated_at.
        completed_status: status de conclusão (default RECEIVED).

    Returns:
        {matched, completed, status, uploaded_count, expected_count, request_id}
    """
    # 1) Push do ficheiro + campos neutros (SEM status)
    neutral_set = {k: v for k, v in set_fields.items() if k != "status"}
    push_result = await db.documents.update_one(
        match_query,
        {
            "$set": {**neutral_set, "updated_at": now},
            "$push": {"attached_files": file_entry},
        },
    )
    if push_result.matched_count == 0:
        return {
            "matched": False,
            "completed": False,
            "status": None,
            "uploaded_count": 0,
            "expected_count": 1,
            "request_id": None,
        }

    request_id = match_query.get("id")
    doc = await db.documents.find_one(
        {"id": request_id} if request_id else match_query,
        {"_id": 0, "id": 1, "status": 1, "attached_files": 1,
         "expected_count": 1, "quantity": 1},
    )
    if not doc:
        # Pedido desapareceu a meio (delete concorrente) — nada a concluir
        return {
            "matched": True,
            "completed": False,
            "status": None,
            "uploaded_count": 0,
            "expected_count": 1,
            "request_id": request_id,
        }

    expected = parse_expected_count(doc)
    uploaded = len(doc.get("attached_files") or [])
    current_status = doc.get("status")

    already_done = current_status in _COMPLETED_PORTAL_STATUSES
    count_reached = uploaded >= expected
    completed = already_done or count_reached

    if count_reached and not already_done:
        # 2) Contagem atingida → concluir o pedido
        await db.documents.update_one(
            {"id": doc["id"]},
            {
                "$set": {
                    "status": completed_status,
                    "uploaded_count": uploaded,
                    "updated_at": now,
                }
            },
        )
        final_status = completed_status
    else:
        # 3) Ainda incompleto → grava apenas o progresso; mantém pendente
        await db.documents.update_one(
            {"id": doc["id"]},
            {"$set": {"uploaded_count": uploaded, "updated_at": now}},
        )
        final_status = current_status

    logger.info(
        f"[PORTAL-COUNTS] Pedido {doc.get('id')} anexado "
        f"({describe_request_progress(doc)}) → status={final_status!r} "
        f"(completed={completed})"
    )

    return {
        "matched": True,
        "completed": completed,
        "status": final_status,
        "uploaded_count": uploaded,
        "expected_count": expected,
        "request_id": doc.get("id"),
    }
