"""List / stats / by-process property endpoints.

Extraído de `routes/properties.py`.
"""
from __future__ import annotations

from typing import List, Optional

from database import db
from models.property import PropertyListItem, PropertyStatus, PropertyType


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
    search: Optional[str] = None
):
    """Listar imóveis com filtros."""
    query = {}
    
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
        query["assigned_agent_id"] = agent_id
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"internal_reference": {"$regex": search, "$options": "i"}},
            {"address.locality": {"$regex": search, "$options": "i"}},
        ]
    
    properties = await db.properties.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    # Converter para formato de listagem
    result = []
    for p in properties:
        result.append(PropertyListItem(
            id=p["id"],
            internal_reference=p.get("internal_reference"),
            title=p["title"],
            property_type=p["property_type"],
            status=p["status"],
            asking_price=p["financials"]["asking_price"],
            municipality=p["address"]["municipality"],
            district=p["address"]["district"],
            bedrooms=p.get("features", {}).get("bedrooms") if p.get("features") else None,
            useful_area=p.get("features", {}).get("useful_area") if p.get("features") else None,
            photo_url=p["photos"][0] if p.get("photos") else None,
            assigned_agent_name=p.get("assigned_agent_name"),
            source_url=p.get("source_url"),
            process_id=p.get("process_id"),
            client_id=p.get("client_id"),
            client_name=p.get("client_name"),
            created_at=p["created_at"]
        ))
    
    return result


async def run_get_property_stats(user: dict):
    """Obter estatísticas dos imóveis."""
    pipeline = [
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_value": {"$sum": "$financials.asking_price"}
            }
        }
    ]
    
    stats_cursor = db.properties.aggregate(pipeline)
    status_stats = {s["_id"]: {"count": s["count"], "total_value": s["total_value"]} 
                    async for s in stats_cursor}
    
    total = await db.properties.count_documents({})
    
    return {
        "total": total,
        "by_status": status_stats,
        "disponivel": status_stats.get("disponivel", {"count": 0, "total_value": 0}),
        "reservado": status_stats.get("reservado", {"count": 0, "total_value": 0}),
        "vendido": status_stats.get("vendido", {"count": 0, "total_value": 0}),
    }


async def run_get_properties_by_process(
    process_id: str,
    user: dict
):
    """Obter imóveis associados a um processo específico."""
    properties = await db.properties.find(
        {"$or": [
            {"process_id": process_id},
            {"interested_clients": process_id}
        ]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    result = []
    for p in properties:
        result.append(PropertyListItem(
            id=p["id"],
            internal_reference=p.get("internal_reference"),
            title=p["title"],
            property_type=p["property_type"],
            status=p["status"],
            asking_price=p["financials"]["asking_price"],
            municipality=p["address"]["municipality"],
            district=p["address"]["district"],
            bedrooms=p.get("features", {}).get("bedrooms") if p.get("features") else None,
            useful_area=p.get("features", {}).get("useful_area") if p.get("features") else None,
            photo_url=p["photos"][0] if p.get("photos") else None,
            assigned_agent_name=p.get("assigned_agent_name"),
            source_url=p.get("source_url"),
            process_id=p.get("process_id"),
            client_id=p.get("client_id"),
            client_name=p.get("client_name"),
            created_at=p["created_at"]
        ))
    
    return result
