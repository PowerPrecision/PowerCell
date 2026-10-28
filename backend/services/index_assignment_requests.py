"""Pedidos de alteração de atribuição do Index (Out 2026) — `/api/index/*pedido*`.

O Index não muda atribuições (`routes/processes._nao_e_o_index`): fica com um processo pelo
«Atribuir a mim» e mais nada. Quando a atribuição de um processo está errada (é de outro
indexador, devia ser de outro consultor, o processo não é para ele…) o Index PEDE à chefia,
com um motivo opcional, e a chefia trata-o pelo fluxo de sempre («Gerir» no processo). O pedido
não mexe em atribuição nenhuma: é um recado com estado.

REGRAS
------
1. **Stealth.** O Index não deixa rasto no `history` do processo: o pedido grava só auditoria.
2. **Um pedido pendente por pessoa e processo** (409 no segundo): a chefia não recebe duplicados.
3. **Rede.** Cada pedido leva o `network_id` do processo e as listagens filtram pelo âmbito de
   PROCESSOS de quem pergunta (`build_tenant_process_condition`): a chefia da rede A nunca vê
   um pedido de um processo da rede B, e um id alheio resolve-se como 404.
4. **A chefia avisada é a da rede do processo** (`gestao_da_rede_do_processo`), nunca toda.
5. **Soft delete** e `update_one` com `$set`, como no resto da casa.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)

PENDENTE = "pendente"
CONCLUIDO = "concluido"
RECUSADO = "recusado"
ESTADOS = (PENDENTE, CONCLUIDO, RECUSADO)
DECISOES = (CONCLUIDO, RECUSADO)

#: Quem trata os pedidos (e é avisado): a chefia da rede, como no alerta de estagnação.
ROLES_DA_CHEFIA = ("diretor", "ceo", "admin", "master")
TIPO_DA_NOTIFICACAO = "index_assignment_request"
MAX_MOTIVO = 1000
LIMITE_DA_LISTA = 200

PROJECCAO_DO_PEDIDO = {
    "_id": 0, "id": 1, "process_id": 1, "process_number": 1, "client_name": 1, "estado": 1,
    "motivo": 1, "requested_by": 1, "requested_by_name": 1, "created_at": 1,
    "indexacao_name": 1, "resolved_by_name": 1, "resolved_at": 1, "nota_da_resolucao": 1,
}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _limpo(texto: Optional[str]) -> Optional[str]:
    valor = (texto or "").strip()
    return valor[:MAX_MOTIVO] or None


async def _processo(process_id: str) -> dict:
    proc = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "network_id": 1, "company_id": 1,
         "company_name": 1, "assigned_indexacao_id": 1, "indexacao_name": 1},
    )
    if not proc:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return proc


async def _auditar(user: dict, process_id: str, accao: str) -> None:
    """Só auditoria (o Index é stealth): nomes de acções, nunca o motivo escrito. Nunca levanta."""
    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=process_id, user=user, action=accao, field="assignment_request",
            metadata={"origem": "index"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Auditoria do pedido de atribuição não gravada: %s", type(exc).__name__)


async def _avisar(destinos: list[str], titulo: str, mensagem: str, process_id: str, link: str) -> None:
    from services.realtime_notifications import send_realtime_notification

    for uid in destinos:
        try:
            await send_realtime_notification(
                uid, titulo, mensagem, TIPO_DA_NOTIFICACAO, link=link, process_id=process_id,
            )
        except Exception as exc:  # noqa: BLE001 — o aviso nunca desfaz o pedido
            logger.warning("[INDEX] Aviso do pedido de atribuição não enviado: %s", type(exc).__name__)


def _dto(doc: dict) -> dict[str, Any]:
    return {k: doc.get(k) for k in PROJECCAO_DO_PEDIDO if k != "_id"}


async def run_pedir_alteracao(user: dict, process_id: str, motivo: Optional[str]) -> dict[str, Any]:
    """O Index pede à chefia que altere a atribuição do processo (motivo opcional)."""
    proc = await _processo(process_id)
    meu_id = (user or {}).get("id")
    if await db.index_assignment_requests.find_one(
        {"process_id": process_id, "requested_by": meu_id, "estado": PENDENTE, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1},
    ):
        raise HTTPException(
            status_code=409,
            detail="Já tem um pedido de alteração pendente para este processo. A chefia foi avisada.",
        )

    pedido = {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "process_number": proc.get("process_number"),
        "client_name": proc.get("client_name"),
        "network_id": proc.get("network_id"),
        "company_id": proc.get("company_id"),
        "indexacao_name": proc.get("indexacao_name"),
        "motivo": _limpo(motivo),
        "estado": PENDENTE,
        "requested_by": meu_id,
        "requested_by_name": (user or {}).get("name"),
        "created_at": _agora(),
        "is_deleted": False,
    }
    await db.index_assignment_requests.insert_one(dict(pedido))
    await _auditar(user, process_id, "Pedido de alteração de atribuição (Index)")

    from services.alert_audience import gestao_da_rede_do_processo

    chefia = [uid for uid in await gestao_da_rede_do_processo(proc, ROLES_DA_CHEFIA) if uid != meu_id]
    numero = proc.get("process_number") or str(process_id)[:8]
    quem = (user or {}).get("name") or "Um indexador"
    mensagem = f"{quem} pede a alteração da atribuição do processo {numero}."
    if pedido["motivo"]:
        mensagem += f" Motivo: {pedido['motivo']}"
    await _avisar(chefia, "Pedido de alteração de atribuição", mensagem, process_id, "/index")
    return {"success": True, "pedido": _dto(pedido)}


async def _ids_no_ambito(user: dict, process_ids: list[str]) -> set[str]:
    """Os processos destes pedidos que quem pergunta pode ver (âmbito de PROCESSOS, com partilhas)."""
    from services.tenant_network import build_tenant_process_condition, com_isolamento

    if not process_ids:
        return set()
    condicao = com_isolamento(await build_tenant_process_condition(user), {
        "id": {"$in": process_ids}, "is_deleted": {"$ne": True},
    })
    docs = await db.processes.find(condicao, {"_id": 0, "id": 1}).to_list(len(process_ids))
    return {d["id"] for d in docs}


async def run_listar_pedidos(
    user: dict, *, so_meus: bool, estado: Optional[str] = PENDENTE, process_id: Optional[str] = None,
) -> dict[str, Any]:
    """Pedidos no âmbito de quem pergunta. O Index (`so_meus`) vê só os seus; a chefia, os da rede."""
    if estado and estado not in ESTADOS:
        raise HTTPException(status_code=422, detail="Estado de pedido desconhecido.")
    filtro: dict[str, Any] = {"is_deleted": {"$ne": True}}
    if estado:
        filtro["estado"] = estado
    if process_id:
        filtro["process_id"] = process_id
    if so_meus:
        filtro["requested_by"] = (user or {}).get("id")
    docs = await db.index_assignment_requests.find(filtro, PROJECCAO_DO_PEDIDO).sort(
        "created_at", -1).to_list(LIMITE_DA_LISTA)
    visiveis = await _ids_no_ambito(user, list({d["process_id"] for d in docs}))
    itens = [_dto(d) for d in docs if d.get("process_id") in visiveis]
    return {"itens": itens, "total": len(itens)}


async def run_resolver_pedido(
    user: dict, pedido_id: str, decisao: str, nota: Optional[str] = None,
) -> dict[str, Any]:
    """A chefia fecha o pedido: «concluido» (atribuição já tratada pelo «Gerir») ou «recusado»."""
    if decisao not in DECISOES:
        raise HTTPException(status_code=422, detail="Decisão inválida.")
    pedido = await db.index_assignment_requests.find_one(
        {"id": pedido_id, "is_deleted": {"$ne": True}}, {"_id": 0},
    )
    # um pedido de outra rede responde como o que não existe
    if not pedido or pedido.get("process_id") not in await _ids_no_ambito(user, [pedido.get("process_id")]):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    nota_limpa = _limpo(nota)
    resultado = await db.index_assignment_requests.update_one(
        {"id": pedido_id, "estado": PENDENTE},
        {"$set": {
            "estado": decisao,
            "resolved_by": (user or {}).get("id"),
            "resolved_by_name": (user or {}).get("name"),
            "resolved_at": _agora(),
            "nota_da_resolucao": nota_limpa,
        }},
    )
    if not resultado.modified_count:
        raise HTTPException(status_code=409, detail="Este pedido já foi tratado.")

    process_id = pedido["process_id"]
    await _auditar(user, process_id, f"Pedido de alteração de atribuição {decisao}")
    numero = pedido.get("process_number") or str(process_id)[:8]
    if decisao == CONCLUIDO:
        titulo, mensagem = "Pedido de atribuição tratado", f"O seu pedido sobre o processo {numero} foi tratado."
    else:
        titulo, mensagem = "Pedido de atribuição recusado", f"O seu pedido sobre o processo {numero} foi recusado."
    if nota_limpa:
        mensagem += f" Nota: {nota_limpa}"
    if pedido.get("requested_by"):
        await _avisar([pedido["requested_by"]], titulo, mensagem, process_id, f"/index/{process_id}")
    return {"success": True, "id": pedido_id, "estado": decisao}
