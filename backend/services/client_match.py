"""
Serviço para Match Cliente-Imóvel
Encontra correspondências entre clientes e imóveis (leads e imóveis angariados)
"""
import logging
from typing import List, Dict, Any, Optional
from database import db

logger = logging.getLogger(__name__)


async def find_matching_properties_for_client(process_id: str) -> List[Dict[str, Any]]:
    """
    Encontra imóveis ANGARIADOS que correspondem ao perfil do cliente.
    Usa a colecção 'properties' (imóveis da agência).
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    if not process:
        return []
    
    financial = process.get("financial_data", {})
    real_estate = process.get("real_estate_data", {})
    
    # Extrair orçamento
    max_price = None
    for field in ["valor_pretendido", "valor_financiamento"]:
        if financial.get(field):
            try:
                max_price = float(str(financial[field]).replace("€", "").replace(" ", "").replace(",", ".").replace(".", ""))
                break
            except:
                pass
    if not max_price and real_estate.get("valor_imovel"):
        try:
            max_price = float(str(real_estate["valor_imovel"]).replace("€", "").replace(" ", "").replace(",", "."))
        except:
            pass
    
    desired_district_raw = real_estate.get("distrito") or real_estate.get("localizacao") or ""
    desired_district = desired_district_raw.lower() if isinstance(desired_district_raw, str) else ""
    desired_municipality_raw = real_estate.get("concelho") or ""
    desired_municipality = desired_municipality_raw.lower() if isinstance(desired_municipality_raw, str) else ""
    desired_typology_raw = real_estate.get("tipologia", "")
    desired_typology = desired_typology_raw if isinstance(desired_typology_raw, str) else ""
    
    # Extrair número de quartos
    desired_bedrooms = None
    if desired_typology:
        try:
            desired_bedrooms = int(desired_typology.upper().replace("T", "").replace("+", ""))
        except:
            pass
    
    # Buscar imóveis disponíveis
    query = {"status": {"$in": ["disponivel", "em_analise"]}}
    properties = await db.properties.find(query, {"_id": 0}).to_list(100)
    
    matches = []
    for prop in properties:
        score = 0
        reasons = []
        
        prop_price = prop.get("financials", {}).get("asking_price")
        prop_district = (prop.get("address", {}).get("district") or "").lower()
        prop_municipality = (prop.get("address", {}).get("municipality") or "").lower()
        prop_bedrooms = prop.get("features", {}).get("bedrooms") if prop.get("features") else None
        prop_area = prop.get("features", {}).get("useful_area") if prop.get("features") else None
        
        # Match por preço (peso: 40)
        if max_price and prop_price:
            if prop_price <= max_price:
                score += 40
                reasons.append(f"Preço dentro do orçamento ({prop_price:,.0f}€ ≤ {max_price:,.0f}€)")
            elif prop_price <= max_price * 1.1:
                score += 25
                reasons.append(f"Preço 10% acima do orçamento")
            elif prop_price <= max_price * 1.2:
                score += 10
                reasons.append(f"Preço 20% acima do orçamento")
        
        # Match por localização (peso: 35)
        if desired_district and prop_district:
            if desired_district in prop_district or prop_district in desired_district:
                score += 25
                reasons.append(f"Distrito compatível ({prop.get('address', {}).get('district')})")
        
        if desired_municipality and prop_municipality:
            if desired_municipality in prop_municipality or prop_municipality in desired_municipality:
                score += 10
                reasons.append(f"Concelho compatível ({prop.get('address', {}).get('municipality')})")
        
        # Match por tipologia (peso: 25)
        if desired_bedrooms is not None and prop_bedrooms is not None:
            if desired_bedrooms == prop_bedrooms:
                score += 25
                reasons.append(f"Tipologia exacta (T{prop_bedrooms})")
            elif abs(desired_bedrooms - prop_bedrooms) == 1:
                score += 15
                reasons.append(f"Tipologia próxima (T{prop_bedrooms})")
        
        if score > 0:
            matches.append({
                "property": {
                    "id": prop["id"],
                    "internal_reference": prop.get("internal_reference"),
                    "title": prop["title"],
                    "price": prop_price,
                    "district": prop.get("address", {}).get("district"),
                    "municipality": prop.get("address", {}).get("municipality"),
                    "bedrooms": prop_bedrooms,
                    "area": prop_area,
                    "photo": prop.get("photos", [None])[0],
                    "status": prop.get("status"),
                },
                "score": score,
                "match_reasons": reasons,
                "source": "angariado"  # Imóvel da agência
            })
    
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:10]


async def find_matching_leads_for_client(process_id: str) -> List[Dict[str, Any]]:
    """
    Encontra leads de imóveis que correspondem ao perfil do cliente.
    
    Critérios de match:
    - Preço dentro do orçamento (valor financiamento ou valor pretendido)
    - Localização (se especificada)
    - Tipologia (se especificada)
    
    Returns:
        Lista de leads compatíveis ordenados por relevância
    """
    # Obter dados do processo/cliente
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )
    
    if not process:
        return []
    
    # Extrair critérios do cliente
    financial = process.get("financial_data", {})
    real_estate = process.get("real_estate_data", {})
    
    max_price = None
    if financial.get("valor_pretendido"):
        try:
            max_price = float(str(financial["valor_pretendido"]).replace("€", "").replace(" ", "").replace(",", "."))
        except:
            pass
    if not max_price and real_estate.get("valor_imovel"):
        try:
            max_price = float(str(real_estate["valor_imovel"]).replace("€", "").replace(" ", "").replace(",", "."))
        except:
            pass
    
    desired_location_raw = real_estate.get("localizacao", "")
    desired_location = desired_location_raw.lower() if isinstance(desired_location_raw, str) and desired_location_raw else None
    desired_typology_raw = real_estate.get("tipologia", "")
    desired_typology = desired_typology_raw.upper() if isinstance(desired_typology_raw, str) and desired_typology_raw else None
    
    # Construir query para leads
    query = {
        "status": {"$in": ["novo", "contactado", "visita_agendada"]},  # Leads disponíveis
    }
    
    # Buscar todos os leads activos
    leads = await db.property_leads.find(query, {"_id": 0}).to_list(length=100)
    
    # Calcular score de match para cada lead
    matches = []
    for lead in leads:
        score = 0
        match_reasons = []
        
        lead_price = lead.get("price")
        lead_location = (lead.get("location") or "").lower()
        lead_typology = (lead.get("typology") or "").upper()
        
        # Match por preço (se o cliente tem orçamento definido)
        if max_price and lead_price:
            if lead_price <= max_price:
                score += 40
                match_reasons.append(f"Preço dentro do orçamento (€{lead_price:,.0f} ≤ €{max_price:,.0f})")
            elif lead_price <= max_price * 1.1:  # 10% acima
                score += 20
                match_reasons.append(f"Preço ligeiramente acima (+{((lead_price/max_price)-1)*100:.0f}%)")
        elif lead_price:
            score += 10  # Bonus pequeno se tem preço
        
        # Match por localização
        if desired_location and lead_location:
            # Verificar se há correspondência parcial
            if desired_location in lead_location or lead_location in desired_location:
                score += 35
                match_reasons.append(f"Localização compatível ({lead.get('location')})")
            else:
                # Verificar palavras comuns
                desired_words = set(desired_location.split())
                lead_words = set(lead_location.split())
                common = desired_words & lead_words
                if common:
                    score += 15
                    match_reasons.append(f"Zona próxima ({', '.join(common)})")
        
        # Match por tipologia
        if desired_typology and lead_typology:
            if desired_typology == lead_typology:
                score += 25
                match_reasons.append(f"Tipologia exacta ({lead_typology})")
            else:
                # Verificar tipologias próximas
                try:
                    desired_num = int(desired_typology.replace("T", "").replace("+", ""))
                    lead_num = int(lead_typology.replace("T", "").replace("+", ""))
                    if abs(desired_num - lead_num) == 1:
                        score += 10
                        match_reasons.append(f"Tipologia próxima ({lead_typology})")
                except:
                    pass
        
        if score > 0:
            matches.append({
                "lead": lead,
                "score": score,
                "match_reasons": match_reasons,
                "source": "lead"  # Lead externo
            })
    
    # Ordenar por score (maior primeiro)
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    return matches[:10]  # Top 10 matches


async def find_all_matches_for_client(process_id: str) -> Dict[str, Any]:
    """
    Encontra TODOS os imóveis compatíveis (angariados + leads externos).
    Combina resultados das duas fontes.
    """
    # Buscar em paralelo
    properties = await find_matching_properties_for_client(process_id)
    leads = await find_matching_leads_for_client(process_id)
    
    # Combinar e ordenar por score
    all_matches = properties + leads
    all_matches.sort(key=lambda x: x["score"], reverse=True)
    
    return {
        "process_id": process_id,
        "total_matches": len(all_matches),
        "from_properties": len(properties),
        "from_leads": len(leads),
        "matches": all_matches[:15],  # Top 15
        "has_perfect_match": any(m["score"] >= 75 for m in all_matches),
    }


async def find_matching_clients_for_property(property_id: str) -> List[Dict[str, Any]]:
    """
    Encontra clientes que podem ter interesse num imóvel ANGARIADO.
    """
    prop = await db.properties.find_one({"id": property_id}, {"_id": 0})
    
    if not prop:
        return []
    
    prop_price = prop.get("financials", {}).get("asking_price")
    prop_district = (prop.get("address", {}).get("district") or "").lower()
    prop_municipality = (prop.get("address", {}).get("municipality") or "").lower()
    prop_bedrooms = prop.get("features", {}).get("bedrooms") if prop.get("features") else None
    
    # Buscar processos activos
    processes = await db.processes.find(
        {"status": {"$nin": ["escriturado", "recusado", "desistiu"]}},
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
         "status": 1, "financial_data": 1, "real_estate_data": 1}
    ).to_list(200)
    
    matches = []
    for process in processes:
        score = 0
        reasons = []
        
        financial = process.get("financial_data", {})
        real_estate = process.get("real_estate_data", {})
        
        # Obter orçamento do cliente
        client_budget = None
        for field in ["valor_pretendido", "valor_financiamento"]:
            if financial.get(field):
                try:
                    client_budget = float(str(financial[field]).replace("€", "").replace(" ", "").replace(",", ".").replace(".", ""))
                    break
                except:
                    pass
        
        client_district_raw = real_estate.get("distrito") or real_estate.get("localizacao") or ""
        client_district = client_district_raw.lower() if isinstance(client_district_raw, str) else ""
        client_typology = real_estate.get("tipologia", "")
        client_bedrooms = None
        if client_typology:
            try:
                client_bedrooms = int(client_typology.upper().replace("T", "").replace("+", ""))
            except:
                pass
        
        # Match por preço
        if prop_price and client_budget:
            if prop_price <= client_budget:
                score += 40
                reasons.append("Dentro do orçamento")
            elif prop_price <= client_budget * 1.15:
                score += 20
                reasons.append("Ligeiramente acima do orçamento")
        
        # Match por localização
        if prop_district and client_district:
            if client_district in prop_district or prop_district in client_district:
                score += 30
                reasons.append(f"Localização desejada ({prop.get('address', {}).get('district')})")
        
        # Match por tipologia
        if prop_bedrooms is not None and client_bedrooms is not None:
            if prop_bedrooms == client_bedrooms:
                score += 25
                reasons.append(f"Tipologia exacta (T{prop_bedrooms})")
            elif abs(prop_bedrooms - client_bedrooms) == 1:
                score += 10
                reasons.append(f"Tipologia próxima")
        
        if score > 0:
            matches.append({
                "process": {
                    "id": process["id"],
                    "client_name": process.get("client_name"),
                    "client_email": process.get("client_email"),
                    "client_phone": process.get("client_phone"),
                    "status": process.get("status"),
                },
                "score": score,
                "match_reasons": reasons,
            })
    
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:10]


async def find_matching_clients_for_lead(lead_id: str) -> List[Dict[str, Any]]:
    """
    Encontra clientes que podem ter interesse num imóvel específico.
    
    Returns:
        Lista de clientes compatíveis ordenados por relevância
    """
    # Obter dados do lead
    lead = await db.property_leads.find_one(
        {"id": lead_id},
        {"_id": 0}
    )
    
    if not lead:
        return []
    
    lead_price = lead.get("price")
    lead_location = (lead.get("location") or "").lower()
    lead_typology = (lead.get("typology") or "").upper()
    lead_area = lead.get("area")
    
    # Buscar processos activos
    processes = await db.processes.find(
        {"status": {"$nin": ["escriturado", "recusado", "desistiu"]}},
        {"_id": 0, "id": 1, "client_name": 1, "status": 1, "financial_data": 1, "real_estate_data": 1}
    ).to_list(length=200)
    
    matches = []
    for process in processes:
        score = 0
        match_reasons = []
        
        financial = process.get("financial_data") or {}
        real_estate = process.get("real_estate_data") or {}
        
        # Obter orçamento do cliente
        client_budget = None
        if financial and financial.get("valor_pretendido"):
            try:
                client_budget = float(str(financial["valor_pretendido"]).replace("€", "").replace(" ", "").replace(",", "."))
            except:
                pass
        if not client_budget and real_estate and real_estate.get("valor_imovel"):
            try:
                client_budget = float(str(real_estate["valor_imovel"]).replace("€", "").replace(" ", "").replace(",", "."))
            except:
                pass
        
        client_location_raw = (real_estate.get("localizacao") if real_estate else "") or ""
        client_location = client_location_raw.lower() if isinstance(client_location_raw, str) else ""
        client_typology_raw = (real_estate.get("tipologia") if real_estate else "") or ""
        client_typology = client_typology_raw.upper() if isinstance(client_typology_raw, str) else ""
        
        # Match por preço
        if lead_price and client_budget:
            if lead_price <= client_budget:
                score += 40
                match_reasons.append(f"Dentro do orçamento")
            elif lead_price <= client_budget * 1.15:
                score += 15
                match_reasons.append(f"Ligeiramente acima do orçamento")
        
        # Match por localização
        if lead_location and client_location:
            if client_location in lead_location or lead_location in client_location:
                score += 35
                match_reasons.append(f"Localização desejada")
        
        # Match por tipologia
        if lead_typology and client_typology:
            if lead_typology == client_typology:
                score += 25
                match_reasons.append(f"Tipologia exacta")
        
        if score > 0:
            matches.append({
                "process": {
                    "id": process["id"],
                    "client_name": process.get("client_name"),
                    "status": process.get("status"),
                },
                "score": score,
                "match_reasons": match_reasons,
            })
    
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    return matches[:10]


async def get_match_summary_for_client(process_id: str) -> Dict[str, Any]:
    """
    Obter resumo de matches para um cliente (propriedades + leads).
    """
    all_matches = await find_all_matches_for_client(process_id)
    
    return {
        "total_matches": all_matches["total_matches"],
        "from_properties": all_matches["from_properties"],
        "from_leads": all_matches["from_leads"],
        "top_matches": all_matches["matches"][:5],
        "has_perfect_match": all_matches["has_perfect_match"],
    }
