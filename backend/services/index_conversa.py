"""Conversa do processo entre o Index e quem o carregou (Out 2026).

O Index precisava de falar com a pessoa que carregou o processo («falta o recibo de Março», «este IRS
é de 2023?») sem sair da bancada. Reaproveita-se o chat interno: cada mensagem é uma mensagem DIRECTA
de `chat_messages` com `process_id` e `canal: "index"`. Assim:

  * o destinatário recebe-a onde já recebe tudo (chat interno, contador de não lidas, tempo real) e
    ainda uma notificação com a ligação ao processo;
  * a conversa do processo é só um filtro (`process_id` + `canal`) — vê-se na bancada do Index e no
    detalhe do processo, e quem substitui o indexador lê o que ficou para trás;
  * a resposta dada no chat interno volta ao processo (`herdar_canal_do_processo`).

QUEM CARREGOU (`resolver_quem_carregou`), por esta ordem:
  1. o carimbo `created_by_id` (gravado na criação desde esta mudança);
  2. o autor do registo «Criou processo» no histórico (processos antigos);
  3. o intermediário (mediador) e depois o consultor atribuídos.
  Nunca um parceiro (outro plano de identidade, sem chat interno) nem um utilizador inactivo.

STEALTH: nada disto escreve no `history` do processo — o Index continua sem deixar rasto no mural.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.realtime_delivery import entregar_a_utilizador
from utils.input_sanitization import sanitize_multiline_text

logger = logging.getLogger(__name__)

CANAL_INDEX = "index"
MAX_MENSAGENS = 200
MAX_CARACTERES = 4000

ERRO_SEM_QUEM_CARREGOU = "Não foi possível identificar quem carregou este processo."
ERRO_SEM_INDEX = "Este processo ainda não tem ninguém do Index atribuído."
ERRO_MENSAGEM_VAZIA = "Escreva a mensagem."

_PROJ_UTILIZADOR = {"_id": 0, "id": 1, "name": 1, "role": 1, "is_active": 1}
_PROJ_PROCESSO = {
    "_id": 0, "id": 1, "process_number": 1, "client_name": 1, "created_by_id": 1,
    "assigned_indexacao_id": 1, "indexacao_name": 1,
    "assigned_mediador_ids": 1, "assigned_mediador_id": 1,
    "assigned_consultor_ids": 1, "assigned_consultor_id": 1,
}


class MensagemDaConversa(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, max_length=MAX_CARACTERES)


def _ids(valor: Any) -> list[str]:
    if isinstance(valor, list):
        return [str(v) for v in valor if v]
    return [str(valor)] if valor else []


async def _utilizador_contactavel(user_id: Optional[str]) -> Optional[dict]:
    if not user_id:
        return None
    u = await db.users.find_one({"id": user_id}, _PROJ_UTILIZADOR)
    if not u or u.get("is_active") is False or u.get("role") == "parceiro":
        return None
    return {"id": u["id"], "name": u.get("name") or "Utilizador"}


async def resolver_quem_carregou(proc: dict) -> Optional[dict]:
    """`{id, name}` de quem carregou o processo, ou None (ver a ordem no topo do módulo)."""
    candidatos: list[str] = []
    candidatos += _ids(proc.get("created_by_id"))
    criacao = await db.history.find_one(
        {"process_id": proc.get("id"), "action": {"$regex": "^Criou processo"}, "user_id": {"$ne": None}},
        {"_id": 0, "user_id": 1},
        sort=[("created_at", 1)],
    )
    if criacao:
        candidatos.append(str(criacao["user_id"]))
    candidatos += _ids(proc.get("assigned_mediador_ids")) or _ids(proc.get("assigned_mediador_id"))
    candidatos += _ids(proc.get("assigned_consultor_ids")) or _ids(proc.get("assigned_consultor_id"))
    vistos: set[str] = set()
    for cid in candidatos:
        if cid in vistos:
            continue
        vistos.add(cid)
        u = await _utilizador_contactavel(cid)
        if u:
            return u
    return None


async def _carregar(process_id: str) -> dict:
    proc = await db.processes.find_one({"id": process_id, "is_deleted": {"$ne": True}}, _PROJ_PROCESSO)
    if not proc:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return proc


def _filtro_da_conversa(process_id: str) -> dict:
    return {"process_id": process_id, "canal": CANAL_INDEX, "group_id": None, "is_deleted": {"$ne": True}}


async def _mensagens(process_id: str, user: dict) -> list[dict]:
    msgs = await db.chat_messages.find(
        _filtro_da_conversa(process_id),
        {"_id": 0, "id": 1, "sender_id": 1, "sender_name": 1, "receiver_id": 1, "receiver_name": 1,
         "content": 1, "created_at": 1, "read": 1, "edited": 1},
    ).sort("created_at", -1).limit(MAX_MENSAGENS).to_list(MAX_MENSAGENS)
    msgs.reverse()
    meu = user.get("id")
    por_ler = [m["id"] for m in msgs if m.get("receiver_id") == meu and not m.get("read")]
    if por_ler:
        agora = datetime.now(timezone.utc).isoformat()
        await db.chat_messages.update_many(
            {"id": {"$in": por_ler}}, {"$set": {"read": True, "read_at": agora}}
        )
        for m in msgs:
            if m["id"] in por_ler:
                m["read"] = True
    for m in msgs:
        m["mine"] = m.get("sender_id") == meu
    return msgs


async def _index_do_processo(proc: dict, user: dict) -> Optional[dict]:
    """O indexador atribuído; sem ele, o último do Index que escreveu na conversa (que não sou eu)."""
    u = await _utilizador_contactavel(proc.get("assigned_indexacao_id"))
    if u:
        return u
    ultima = await db.chat_messages.find_one(
        {**_filtro_da_conversa(proc["id"]), "lado": "index", "sender_id": {"$ne": user.get("id")}},
        {"_id": 0, "sender_id": 1},
        sort=[("created_at", -1)],
    )
    return await _utilizador_contactavel((ultima or {}).get("sender_id"))


# ====================================================================
# LEITURA
# ====================================================================
async def run_ler_conversa_do_index(user: dict, process_id: str) -> dict[str, Any]:
    """Bancada do Index: a conversa com quem carregou o processo."""
    proc = await _carregar(process_id)
    return {
        "interlocutor": await resolver_quem_carregou(proc),
        "messages": await _mensagens(process_id, user),
    }


async def run_ler_conversa_do_processo(user: dict, process_id: str) -> dict[str, Any]:
    """Detalhe do processo: a mesma conversa, vista do lado de quem carregou."""
    proc = await _carregar(process_id)
    return {
        "interlocutor": await _index_do_processo(proc, user),
        "messages": await _mensagens(process_id, user),
    }


# ====================================================================
# ESCRITA
# ====================================================================
async def _gravar_e_entregar(
    user: dict, proc: dict, destinatario: dict, texto: str, *, lado: str, link: str
) -> dict:
    conteudo = sanitize_multiline_text(texto, max_length=MAX_CARACTERES)
    if not (conteudo or "").strip():
        raise HTTPException(status_code=400, detail=ERRO_MENSAGEM_VAZIA)
    agora = datetime.now(timezone.utc).isoformat()
    msg = {
        "id": str(uuid4()),
        "sender_id": user.get("id"),
        "sender_name": user.get("name", ""),
        "receiver_id": destinatario["id"],
        "receiver_name": destinatario["name"],
        "content": conteudo,
        "process_id": proc["id"],
        "process_number": proc.get("process_number"),
        "canal": CANAL_INDEX,
        "lado": lado,
        "group_id": None,
        "reply_to": None,
        "reactions": [],
        "attachments": [],
        "edited": False,
        "read": False,
        "created_at": agora,
    }
    await db.chat_messages.insert_one(msg)
    msg.pop("_id", None)

    # os efeitos nunca fazem falhar a mensagem, que já está gravada
    try:
        await entregar_a_utilizador(
            destinatario["id"],
            "new_chat_message",
            {
                "id": msg["id"], "sender_id": msg["sender_id"], "sender_name": msg["sender_name"],
                "receiver_id": destinatario["id"], "content": conteudo[:100], "process_id": proc["id"],
                "canal": CANAL_INDEX, "created_at": agora,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX-CONVERSA] Entrega em tempo real falhou: %s", type(exc).__name__)
    try:
        from services.realtime_notifications import send_realtime_notification

        ref = f"#{proc['process_number']}" if proc.get("process_number") else (proc.get("client_name") or "")
        titulo = (
            f"Mensagem do Index sobre o processo {ref}".strip()
            if lado == "index"
            else f"Resposta sobre o processo {ref}".strip()
        )
        await send_realtime_notification(
            user_id=destinatario["id"], title=titulo,
            message=f"{msg['sender_name'] or 'Alguém'}: {conteudo[:140]}",
            notification_type="index_conversa", link=link, process_id=proc["id"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX-CONVERSA] Notificação não enviada: %s", type(exc).__name__)

    msg["mine"] = True
    return {"success": True, "message": msg}


async def run_enviar_do_index(user: dict, process_id: str, data: MensagemDaConversa) -> dict:
    proc = await _carregar(process_id)
    destinatario = await resolver_quem_carregou(proc)
    if not destinatario or destinatario["id"] == user.get("id"):
        raise HTTPException(status_code=409, detail=ERRO_SEM_QUEM_CARREGOU)
    return await _gravar_e_entregar(
        user, proc, destinatario, data.text, lado="index", link=f"/processo/{process_id}?tab=resumo"
    )


async def run_enviar_do_processo(user: dict, process_id: str, data: MensagemDaConversa) -> dict:
    proc = await _carregar(process_id)
    destinatario = await _index_do_processo(proc, user)
    if not destinatario or destinatario["id"] == user.get("id"):
        raise HTTPException(status_code=409, detail=ERRO_SEM_INDEX)
    return await _gravar_e_entregar(
        user, proc, destinatario, data.text, lado="processo", link=f"/index/{process_id}"
    )


# ====================================================================
# CHAT INTERNO — a resposta volta ao processo
# ====================================================================
_PROJ_BASE = {"_id": 0, "canal": 1, "process_id": 1, "process_number": 1, "sender_id": 1, "lado": 1}


async def herdar_canal_do_processo(
    sender_id: str, receiver_id: str, reply_to: Optional[str], *, mensagens=None
) -> dict:
    """Campos a herdar por uma mensagem directa enviada pelo chat interno.

    Responder (citando) a uma mensagem da conversa de um processo, ou simplesmente responder quando a
    última mensagem entre os dois é dessa conversa, mantém a resposta no processo. Sem isto, quem
    carregou respondia no chat e o Index nunca a via na bancada.

    `mensagens` é a colecção do chamador (o chat interno lê a sua própria `db`).
    """
    mensagens = mensagens if mensagens is not None else db.chat_messages
    entre_os_dois = {"$or": [
        {"sender_id": sender_id, "receiver_id": receiver_id},
        {"sender_id": receiver_id, "receiver_id": sender_id},
    ], "group_id": None}
    base = None
    if reply_to:
        base = await mensagens.find_one({"id": reply_to, **entre_os_dois}, _PROJ_BASE)
    if not base:
        base = await mensagens.find_one(entre_os_dois, _PROJ_BASE, sort=[("created_at", -1)])
    if not base or base.get("canal") != CANAL_INDEX or not base.get("process_id"):
        return {}
    lado = base.get("lado") or "processo"
    if base.get("sender_id") != sender_id:
        # responde-se ao outro lado
        lado = "processo" if lado == "index" else "index"
    return {
        "canal": CANAL_INDEX,
        "process_id": base["process_id"],
        "process_number": base.get("process_number"),
        "lado": lado,
    }
