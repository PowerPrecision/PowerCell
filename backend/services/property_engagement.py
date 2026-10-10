"""Interested clients, visits, and photo ops.

Extraído de `routes/properties.py`.

FRONTEIRA DE REDE (D-24) — e aqui estão as DUAS perguntas:

* o IMÓVEL (`exigir_imovel_no_ambito`): os cinco handlers eram
  `find_one({"id": property_id})` e mais nada;
* o DESTINO (`pode_apontar_para_o_processo`): o `client_id` destas rotas
  é um **process_id**, e tanto o "cliente interessado" como o "registar
  visita" leem `db.processes` e gravam o `client_name` que lá encontram
  no histórico do imóvel. Sem a segunda pergunta, quem soubesse um id de
  processo de outra rede copiava o nome do cliente para a sua carteira —
  e ficava lá escrito.
"""
from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db
from models.property import PropertyHistory
from services.property_scope import (
    ERRO_IMOVEL_NAO_ENCONTRADO,
    PROJECCAO_DE_POSSE,
    exigir_imovel_no_ambito,
    pode_apontar_para_o_processo,
)
from services.tenant_network import PROJECCAO_DO_CARIMBO

#: A MESMA mensagem para "não existe" e para "não é da tua rede": o
#: código de resposta de um destino não pode ser um oráculo sobre os
#: processos das outras redes.
ERRO_CLIENTE_NAO_ENCONTRADO = "Cliente não encontrado"

logger = logging.getLogger(__name__)


async def run_add_interested_client(
    property_id: str,
    client_id: str,
    user: dict,
    request: Request | None = None,
):
    """Adicionar cliente interessado a um imóvel.

    `client_id` é um **process_id** (o nome é legado).
    """
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail=ERRO_IMOVEL_NAO_ENCONTRADO)

    contexto = await exigir_imovel_no_ambito(
        prop, user=user, request=request, escrita=True
    )

    # O DESTINO: o `client_name` deste processo vai ser gravado no
    # histórico do imóvel.
    process = await db.processes.find_one({"id": client_id})
    if not pode_apontar_para_o_processo(
        process, papel=contexto.papel, scope=contexto.scope
    ):
        raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)
    
    # Adicionar se não existe
    if client_id not in prop.get("interested_clients", []):
        now = datetime.now(timezone.utc).isoformat()
        await db.properties.update_one(
            {"id": property_id},
            {
                "$addToSet": {"interested_clients": client_id},
                "$inc": {"inquiry_count": 1},
                "$push": {
                    "history": PropertyHistory(
                        timestamp=now,
                        event=f"Cliente interessado: {process.get('client_name')}",
                        user=user.get("email")
                    ).model_dump()
                }
            }
        )
    
    return {"success": True, "message": f"Cliente {process.get('client_name')} adicionado"}


async def run_get_interested_clients(
    property_id: str,
    user: dict,
    request: Request | None = None,
):
    """Obter lista de clientes interessados num imóvel.

    A projecção LEVA o carimbo: com `{"interested_clients": 1}` o
    documento chegava sem rede, contava como legado e a guarda ABRIA —
    é a nota da `PROJECCAO_DE_POSSE`.
    """
    prop = await db.properties.find_one(
        {"id": property_id},
        {"interested_clients": 1, **PROJECCAO_DE_POSSE},
    )

    if not prop:
        raise HTTPException(status_code=404, detail=ERRO_IMOVEL_NAO_ENCONTRADO)

    await exigir_imovel_no_ambito(prop, user=user, request=request)
    
    client_ids = prop.get("interested_clients", [])
    
    if not client_ids:
        return []
    
    clients = await db.processes.find(
        {"id": {"$in": client_ids}},
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, "status": 1}
    ).to_list(100)
    
    return clients


async def run_register_visit(
    property_id: str,
    user: dict,
    client_id: Optional[str] = None,
    notes: Optional[str] = None,
    request: Request | None = None,
):
    """Registar uma visita ao imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail=ERRO_IMOVEL_NAO_ENCONTRADO)

    contexto = await exigir_imovel_no_ambito(
        prop, user=user, request=request, escrita=True
    )

    now = datetime.now(timezone.utc).isoformat()

    event_text = "Visita registada"
    if client_id:
        process = await db.processes.find_one(
            {"id": client_id},
            {"client_name": 1, **PROJECCAO_DO_CARIMBO},
        )
        # O DESTINO outra vez: sem isto, o nome do cliente de outra rede
        # entrava no histórico do imóvel. Recusa-se em vez de ignorar o
        # nome — gravar "Visita registada" sem dizer porquê deixava a
        # pessoa a pensar que o id estava certo.
        if not pode_apontar_para_o_processo(
            process, papel=contexto.papel, scope=contexto.scope
        ):
            raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)
        event_text = f"Visita com {process.get('client_name')}"
    
    if notes:
        event_text += f" - {notes}"
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$inc": {"visit_count": 1},
            "$push": {
                "history": PropertyHistory(
                    timestamp=now,
                    event=event_text,
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Visita registada"}


async def run_upload_property_photo(
    property_id: str,
    photo_url: str,
    user: dict,
    request: Request | None = None,
):
    """
    Adicionar foto a um imóvel.
    Aceita URL de foto (pode ser do OneDrive, Dropbox, etc.)
    """
    prop = await db.properties.find_one({"id": property_id}, PROJECCAO_DE_POSSE)
    if not prop:
        raise HTTPException(status_code=404, detail=ERRO_IMOVEL_NAO_ENCONTRADO)

    await exigir_imovel_no_ambito(prop, user=user, request=request, escrita=True)
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$addToSet": {"photos": photo_url},
            "$set": {"updated_at": now},
            "$push": {
                "history": PropertyHistory(
                    timestamp=now,
                    event="Foto adicionada",
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Foto adicionada", "photo_url": photo_url}


async def run_remove_property_photo(
    property_id: str,
    photo_url: str,
    user: dict,
    request: Request | None = None,
):
    """Remover foto de um imóvel."""
    prop = await db.properties.find_one({"id": property_id}, PROJECCAO_DE_POSSE)
    if not prop:
        raise HTTPException(status_code=404, detail=ERRO_IMOVEL_NAO_ENCONTRADO)

    await exigir_imovel_no_ambito(prop, user=user, request=request, escrita=True)
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$pull": {"photos": photo_url},
            "$set": {"updated_at": now}
        }
    )
    
    return {"success": True, "message": "Foto removida"}
