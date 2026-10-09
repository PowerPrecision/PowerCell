"""List / stats / by-process property endpoints.

Extraído de `routes/properties.py`.

FRONTEIRA DE REDE (D-24): as três listagens entram pelo
`property_scope`. Antes abriam com `query = {}` e o `/stats` contava e
SOMAVA a colecção inteira — a Domus lia o valor da carteira do grupo.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import Request

from database import db
from models.property import PropertyListItem, PropertyStatus, PropertyType
from services.property_scope import carregar_contexto_dos_imoveis
from services.tenant_network import com_isolamento


def _para_item_de_listagem(p: dict) -> PropertyListItem:
    """Documento → item de listagem.

    Ponto único: esta conversão existia em DUAS cópias neste ficheiro, e
    `client_name` viaja aqui — o campo que faz a listagem, por si só,
    entregar o nome do cliente da outra rede.
    """
    features = p.get("features") or {}
    return PropertyListItem(
        id=p["id"],
        internal_reference=p.get("internal_reference"),
        title=p["title"],
        property_type=p["property_type"],
        status=p["status"],
        asking_price=p["financials"]["asking_price"],
        municipality=p["address"]["municipality"],
        district=p["address"]["district"],
        bedrooms=features.get("bedrooms"),
        useful_area=features.get("useful_area"),
        photo_url=p["photos"][0] if p.get("photos") else None,
        assigned_agent_name=p.get("assigned_agent_name"),
        source_url=p.get("source_url"),
        process_id=p.get("process_id"),
        client_id=p.get("client_id"),
        client_name=p.get("client_name"),
        created_at=p["created_at"],
    )


async def run_list_properties(
    user: dict,
    status: Optional[PropertyStatus] = None,
    property_type: Optional[PropertyType] = None,
    district: Optional[str] = None,
    municipality: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_bedrooms: Optional[int] = None,
    agent_id: Optional[str] = None,
    search: Optional[str] = None,
    request: Optional[Request] = None,
) -> List[PropertyListItem]:
    """Listar imóveis com filtros — dentro da rede do utilizador."""
    query: dict = {}

    if status:
        query["status"] = status
    if property_type:
        query["property_type"] = property_type
    if district:
        query["address.district"] = {"$regex": district, "$options": "i"}
    if municipality:
        query["address.municipality"] = {"$regex": municipality, "$options": "i"}
    if min_price:
        query["financials.asking_price"] = {"$gte": min_price}
    if max_price:
        query.setdefault("financials.asking_price", {})["$lte"] = max_price
    if min_bedrooms:
        query["features.bedrooms"] = {"$gte": min_bedrooms}
    if agent_id:
        # `agent_id` é um FILTRO de conveniência e nunca foi uma
        # fronteira — a fronteira é a rede, aplicada por fora.
        query["assigned_agent_id"] = agent_id
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"internal_reference": {"$regex": search, "$options": "i"}},
            {"address.locality": {"$regex": search, "$options": "i"}},
        ]

    contexto = await carregar_contexto_dos_imoveis(user, request)
    consulta = com_isolamento(contexto.condicao, query) if contexto.condicao else query

    properties = await db.properties.find(consulta, {"_id": 0}).sort(
        "created_at", -1
    ).to_list(500)

    return [_para_item_de_listagem(p) for p in properties]


async def run_get_property_stats(user: dict, request: Optional[Request] = None):
    """Estatísticas da carteira — da rede do utilizador, não do sistema.

    O `$match` entra ANTES do `$group`: agregar primeiro e filtrar
    depois somaria o valor das outras redes para o descartar a seguir,
    e o `total` sairia errado de qualquer maneira.
    """
    contexto = await carregar_contexto_dos_imoveis(user, request)

    pipeline: list[dict] = []
    if contexto.condicao:
        pipeline.append({"$match": contexto.condicao})
    pipeline.append({
        "$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_value": {"$sum": "$financials.asking_price"},
        }
    })

    stats_cursor = db.properties.aggregate(pipeline)
    status_stats = {
        s["_id"]: {"count": s["count"], "total_value": s["total_value"]}
        async for s in stats_cursor
    }

    total = await db.properties.count_documents(contexto.condicao or {})

    return {
        "total": total,
        "by_status": status_stats,
        "disponivel": status_stats.get("disponivel", {"count": 0, "total_value": 0}),
        "reservado": status_stats.get("reservado", {"count": 0, "total_value": 0}),
        "vendido": status_stats.get("vendido", {"count": 0, "total_value": 0}),
    }


async def run_get_properties_by_process(
    process_id: str,
    user: dict,
    request: Optional[Request] = None,
) -> List[PropertyListItem]:
    """Imóveis de um processo.

    O `process_id` vem do URL: sem a condição de rede, bastava conhecer
    um id de processo de outra rede para enumerar a carteira ligada a
    ele. `interested_clients` guarda **process_ids** — o nome é legado.
    """
    query = {
        "$or": [
            {"process_id": process_id},
            {"interested_clients": process_id},
        ]
    }

    contexto = await carregar_contexto_dos_imoveis(user, request)
    consulta = com_isolamento(contexto.condicao, query) if contexto.condicao else query

    properties = await db.properties.find(consulta, {"_id": 0}).sort(
        "created_at", -1
    ).to_list(100)

    return [_para_item_de_listagem(p) for p in properties]
