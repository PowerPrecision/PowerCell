"""«Documentos novos do cliente» — a bolinha verde das listas e do Kanban (Bloco 2).

O DEFEITO QUE ISTO FECHA
========================
`fetch_new_documents_map` perguntava por `db.documents` com
`status == "uploaded"` (minúsculas). O Portal nunca escreve esse estado: o
upload do cliente cria o registo — ou conclui o pedido — com
`status: "RECEIVED"` e `uploaded_by: "portal_client"`. A bolinha verde estava
desenhada em três ecrãs (Kanban, «Os Meus Processos», listagem filtrada) e **não
acendia nunca**: a UI lia um contrato que o servidor não cumpria, e uma
bolinha que não acende não produz erro nenhum.

A REGRA (um sítio só, partilhado por quem pergunta e por quem limpa)
====================================================================
Um documento é NOVO quando:
  1. foi enviado pelo cliente (`uploaded_by == "portal_client"`) ou está no
     estado legado `uploaded`;
  2. a equipa ainda não o viu (`staff_seen_at` ausente);
  3. é recente (`JANELA_DE_NOVIDADE_DIAS`). Sem esta janela, a primeira
     passagem em produção acenderia a bolinha em TODOS os processos com
     algum upload do Portal, para sempre — e uma bolinha em todo o lado
     deixa de dizer fosse o que fosse.

«Visto» é abrir a lista de documentos do processo (`marcar_como_vistos`).
Guarda-se **quando** e não **quem**: o perfil `indexacao` não deixa rasto, e a
bolinha só precisa de saber que alguém da equipa olhou.

`condicao_de_documento_novo` é a ÚNICA definição: o mapa das listagens e a
limpeza usam-na, porque duas respostas à mesma pergunta divergem sem dar erro
(o predicado e a condição Mongo do Sub35).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

JANELA_DE_NOVIDADE_DIAS = 30
ENVIADO_PELO_CLIENTE = "portal_client"
#: O Portal do Parceiro grava `uploaded_by = "partner:<id>"`. Um documento
#: enviado por um parceiro é, para a equipa, tão «novo» como o do cliente —
#: sem isto a bolinha verde nunca acendia para o que o parceiro envia.
PREFIXO_DE_AUTORIA_DO_PARCEIRO = "partner:"
ESTADOS_LEGADOS = ("uploaded", "UPLOADED")


def condicao_de_documento_novo(agora: Optional[datetime] = None) -> dict[str, Any]:
    """A condição Mongo de «documento novo do cliente» (sem o filtro de processo)."""
    agora = agora or datetime.now(timezone.utc)
    limite = (agora - timedelta(days=JANELA_DE_NOVIDADE_DIAS)).isoformat()
    return {"$and": [
        {"$or": [
            {"uploaded_by": ENVIADO_PELO_CLIENTE},
            {"uploaded_by": {"$regex": f"^{PREFIXO_DE_AUTORIA_DO_PARCEIRO}"}},
            {"status": {"$in": list(ESTADOS_LEGADOS)}},
        ]},
        {"staff_seen_at": {"$in": [None, ""]}},
        {"uploaded_at": {"$gte": limite}},
    ]}


async def mapa_de_documentos_novos(process_ids: list[str]) -> dict[str, bool]:
    """process_id → tem documentos novos do cliente."""
    ids = [p for p in (process_ids or []) if p]
    if not ids:
        return {}
    rows = await db.documents.aggregate([
        {"$match": {"$and": [{"process_id": {"$in": ids}}, condicao_de_documento_novo()]}},
        {"$group": {"_id": "$process_id", "novos": {"$sum": 1}}},
    ]).to_list(1000)
    return {r["_id"]: r["novos"] > 0 for r in rows}


async def marcar_como_vistos(process_id: str) -> int:
    """A equipa abriu os documentos: o que era novo deixa de o ser. Nunca propaga."""
    if not process_id:
        return 0
    try:
        resultado = await db.documents.update_many(
            {"$and": [{"process_id": process_id}, condicao_de_documento_novo()]},
            {"$set": {"staff_seen_at": datetime.now(timezone.utc).isoformat()}},
        )
        return int(getattr(resultado, "modified_count", 0) or 0)
    except Exception as exc:
        logger.warning(
            "[DOC-NOVELTY] Não foi possível marcar os documentos de %s como vistos: %s",
            process_id, exc,
        )
        return 0
