"""Smart match (process → properties) handler.

Extraído de `routes/match.py`.
Do **not** overwrite services/client_match.py.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def run_smart_match_for_process(process_id: str, user: dict):
    """
    Smart Match: Encontra imóveis angariados compatíveis com os critérios
    de compra de um processo (comprador).
    """
    # 1. Buscar o processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # 2. Verificar se é processo de comprador
    process_type = process.get("process_type", "")
    real_estate = process.get("real_estate_data", {}) or {}

    # Determinar tipo: se tem finalidade "compra" ou process_type contém compra/habitacao
    is_buyer = (
        "compra" in (process_type or "").lower() or
        "habitacao" in (process_type or "").lower() or
        "credito_habitacao" in (process_type or "").lower() or
        real_estate.get("finalidade", "").lower() == "compra" or
        real_estate.get("ja_tem_imovel") is False or
        real_estate.get("has_property") is False
    )

    if not is_buyer:
        return {
            "process_id": process_id,
            "is_buyer": False,
            "message": "Apenas para processos de Comprador",
            "criteria": None,
            "total_matches": 0,
            "matches": [],
        }

    # 3. Extrair critérios de pesquisa
    # Orçamento: tentar vários campos
    max_price = None
    for field in ["valor_maximo_imovel", "valor_imovel", "orcamento_max"]:
        val = real_estate.get(field)
        if val:
            try:
                max_price = float(str(val).replace("€", "").replace(" ", "").replace(".", "").replace(",", "."))
                break
            except (ValueError, TypeError):
                pass

    # Se não encontrou no real_estate, tentar financial_data
    if not max_price:
        financial = process.get("financial_data", {}) or {}
        for field in ["valor_pretendido", "valor_financiamento"]:
            val = financial.get(field)
            if val:
                try:
                    max_price = float(str(val).replace("€", "").replace(" ", "").replace(".", "").replace(",", "."))
                    break
                except (ValueError, TypeError):
                    pass

    # Tipologia (ex: T2, T3)
    tipologia = real_estate.get("tipologia", "")
    desired_bedrooms = None
    if tipologia:
        try:
            desired_bedrooms = int(str(tipologia).upper().replace("T", "").replace("+", "").strip())
        except (ValueError, TypeError):
            pass

    # Localização (concelho/municipality)
    concelho = real_estate.get("concelho", "") or real_estate.get("localizacao", "")
    distrito = real_estate.get("distrito", "")

    # Área pretendida
    area_pretendida = real_estate.get("area_pretendida")

    criteria = {
        "max_price": max_price,
        "tipologia": tipologia,
        "desired_bedrooms": desired_bedrooms,
        "concelho": concelho,
        "distrito": distrito,
        "area_pretendida": area_pretendida,
    }

    # 4. Construir query MongoDB
    # ─────────────────────────────────────────────────────────────
    # QUERY MONGODB — A VALIDAR PELO UTILIZADOR
    # ─────────────────────────────────────────────────────────────
    query = {
        "status": "disponivel"
    }

    # Filtro por preço: property.financials.asking_price <= orcamento_max
    if max_price:
        query["financials.asking_price"] = {"$lte": max_price}

    # Filtro por concelho: property.address.municipality (case-insensitive)
    if concelho:
        query["address.municipality"] = {"$regex": concelho, "$options": "i"}

    # Filtro por distrito (fallback se não houver concelho)
    if distrito and not concelho:
        query["address.district"] = {"$regex": distrito, "$options": "i"}

    # Filtro por tipologia: property.property_type (case-insensitive)
    if tipologia:
        query["$or"] = [
            {"property_type": {"$regex": tipologia, "$options": "i"}},
            {"features.bedrooms": desired_bedrooms},
        ]

    # Filtro por área pretendida: property.features.useful_area >= area_pretendida * 0.8
    if area_pretendida:
        min_area = area_pretendida * 0.8
        query["features.useful_area"] = {"$gte": min_area}
    # ─────────────────────────────────────────────────────────────

    logger.info(f"[SMART MATCH] Query para processo {process_id}: {query}")

    # 5. Executar query
    properties = await db.properties.find(query, {"_id": 0}).to_list(50)

    # 6. Calcular score de relevância e enriquecer resultados
    matches = []
    for prop in properties:
        score = 0
        reasons = []

        prop_price = prop.get("financials", {}).get("asking_price") if prop.get("financials") else None
        prop_municipality = (prop.get("address", {}).get("municipality") or "") if prop.get("address") else ""
        prop_district = (prop.get("address", {}).get("district") or "") if prop.get("address") else ""
        prop_bedrooms = prop.get("features", {}).get("bedrooms") if prop.get("features") else None
        prop_area = prop.get("features", {}).get("useful_area") if prop.get("features") else None

        # Score por preço (peso 35)
        if max_price and prop_price:
            ratio = prop_price / max_price
            if ratio <= 1.0:
                score += 35
                reasons.append(f"Dentro do orçamento ({prop_price:,.0f}€ ≤ {max_price:,.0f}€)")
            elif ratio <= 1.1:
                score += 20
                reasons.append("Preço 10% acima do orçamento")
            elif ratio <= 1.2:
                score += 10
                reasons.append("Preço 20% acima do orçamento")

        # Score por localização (peso 35)
        if concelho and prop_municipality:
            if concelho.lower() in prop_municipality.lower() or prop_municipality.lower() in concelho.lower():
                score += 35
                reasons.append(f"Concelho compatível ({prop_municipality})")
        if distrito and prop_district:
            if distrito.lower() in prop_district.lower() or prop_district.lower() in distrito.lower():
                score += 15 if score < 35 else 0
                if not any("Concelho" in r for r in reasons):
                    reasons.append(f"Distrito compatível ({prop_district})")

        # Score por tipologia (peso 30)
        if desired_bedrooms is not None and prop_bedrooms is not None:
            if desired_bedrooms == prop_bedrooms:
                score += 30
                reasons.append(f"Tipologia exacta (T{prop_bedrooms})")
            elif abs(desired_bedrooms - prop_bedrooms) == 1:
                score += 15
                reasons.append(f"Tipologia próxima (T{prop_bedrooms})")

        # Score por área
        if area_pretendida and prop_area:
            if prop_area >= area_pretendida:
                score += 10
                reasons.append(f"Área adequada ({prop_area}m²)")
            elif prop_area >= area_pretendida * 0.8:
                score += 5
                reasons.append(f"Área próxima ({prop_area}m²)")

        # Foto principal
        photos = prop.get("photos", [])
        main_photo = photos[0] if photos else None

        matches.append({
            "property_id": prop.get("id"),
            "internal_reference": prop.get("internal_reference"),
            "title": prop.get("title", "Sem título"),
            "price": prop_price,
            "property_type": prop.get("property_type"),
            "bedrooms": prop_bedrooms,
            "area": prop_area,
            "municipality": prop_municipality,
            "district": prop_district,
            "photo": main_photo,
            "status": prop.get("status"),
            "score": score,
            "match_reasons": reasons,
        })

    # Ordenar por score (desc) e depois por preço (asc)
    matches.sort(key=lambda x: (-x["score"], x["price"] or float("inf")))

    return {
        "process_id": process_id,
        "is_buyer": True,
        "criteria": criteria,
        "mongo_query": query,
        "total_matches": len(matches),
        "matches": matches[:20],
    }
