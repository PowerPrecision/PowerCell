"""Smart Match — recomendações de imóveis no Portal.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def run_create_recommendations(data: dict, user: dict):
    """
    Adiciona imóveis recomendados ao perfil do processo/cliente.

    Payload:
    - client_id: ID do cliente (obrigatório)
    - process_id: ID do processo (obrigatório)
    - property_ids: Lista de IDs de imóveis recomendados (obrigatório)

    Os imóveis ficam guardados na lista 'recommended_properties' do processo,
    para serem consumidos pelo Portal do Cliente.
    """
    client_id = data.get("client_id")
    process_id = data.get("process_id")
    property_ids = data.get("property_ids", [])

    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")
    if not property_ids:
        raise HTTPException(status_code=400, detail="property_ids não pode estar vazio")

    # Verificar que o processo existe
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Buscar detalhes dos imóveis
    properties = await db.properties.find(
        {"id": {"$in": property_ids}},
        {"_id": 0}
    ).to_list(50)

    # Criar entrada de recomendação
    now = datetime.now(timezone.utc).isoformat()
    new_recommendations = []

    for prop in properties:
        prop_price = prop.get("financials", {}).get("asking_price") if prop.get("financials") else None
        photos = prop.get("photos", [])
        main_photo = photos[0] if photos else None

        new_recommendations.append({
            "property_id": prop.get("id"),
            "internal_reference": prop.get("internal_reference"),
            "title": prop.get("title", "Sem título"),
            "price": prop_price,
            "property_type": prop.get("property_type"),
            "bedrooms": prop.get("features", {}).get("bedrooms") if prop.get("features") else None,
            "area": prop.get("features", {}).get("useful_area") if prop.get("features") else None,
            "municipality": (prop.get("address", {}).get("municipality") or "") if prop.get("address") else "",
            "district": (prop.get("address", {}).get("district") or "") if prop.get("address") else "",
            "photo": main_photo,
            "recommended_at": now,
            "recommended_by": user.get("id"),
            "recommended_by_name": user.get("name", "Consultor"),
            "viewed_by_client": False,
        })

    # Adicionar ao processo (append para não sobrescrever recomendações anteriores)
    existing = process.get("recommended_properties", [])

    # Remover duplicados (se já existia uma recomendação para o mesmo imóvel)
    existing_ids = {r.get("property_id") for r in existing}
    unique_new = [r for r in new_recommendations if r["property_id"] not in existing_ids]

    updated_recommendations = existing + unique_new

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "recommended_properties": updated_recommendations,
            "updated_at": now,
        }}
    )

    # Registar no histórico
    try:
        from services.history import log_history
        prop_names = ", ".join([r["title"] for r in unique_new[:5]])
        await log_history(
            process_id,
            user=user,
            action="PROPERTY_RECOMMENDED",
            field="recommended_properties",
            old_value=None,
            new_value=f"{len(unique_new)} imóvel(ns) recomendado(s): {prop_names}"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao registar histórico de recomendação: {e}")

    logger.info(
        f"[SMART MATCH] {len(unique_new)} imóveis recomendados pelo consultor "
        f"{user.get('name', 'N/A')} para o processo {process_id}"
    )

    return {
        "success": True,
        "added_count": len(unique_new),
        "total_recommendations": len(updated_recommendations),
        "recommendations": unique_new,
    }


async def run_get_recommendations_for_client(client_data: dict):
    """
    Obtém a lista de imóveis recomendados pelo consultor para este processo.
    Endpoint consumido pelo Portal do Cliente.

    Também marca as recomendações como visualizadas pelo cliente.
    """
    process = client_data["process"]
    process_id = process["id"]

    recommendations = process.get("recommended_properties", [])

    # Marcar como visualizadas pelo cliente
    if recommendations:
        now = datetime.now(timezone.utc).isoformat()
        updated_recs = []
        for rec in recommendations:
            if not rec.get("viewed_by_client"):
                rec["viewed_by_client"] = True
                rec["viewed_at"] = now
            updated_recs.append(rec)

        await db.processes.update_one(
            {"id": process_id},
            {"$set": {"recommended_properties": updated_recs}}
        )

    return {
        "process_id": process_id,
        "total": len(recommendations),
        "recommendations": recommendations,
    }


