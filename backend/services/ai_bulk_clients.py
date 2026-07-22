"""Client suggest/check/list/diagnose handlers for AI bulk import.

Extraído de `routes/ai_bulk.py`.
"""
from __future__ import annotations

from typing import Tuple

from database import db
from routes.ai_bulk.matching import find_client_by_name, suggest_similar_clients


async def run_suggest_clients(
    query: str,
    user: dict,
    limit: int = 5,
):
    """Retornar clientes similares para selecção manual."""
    if not query or len(query) < 2:
        return {
            "query": query,
            "suggestions": [],
            "message": "Query deve ter pelo menos 2 caracteres"
        }
    
    limit = min(limit, 10)
    suggestions = await suggest_similar_clients(query, limit)
    
    return {
        "query": query,
        "total_matches": len(suggestions),
        "suggestions": suggestions
    }



async def run_check_client_exists(
    name: str,
    user: dict,
):
    """Verificar se um cliente existe pelo nome."""
    if not name:
        return {"exists": False, "client": None}
    
    process = await find_client_by_name(name)
    
    if process:
        return {
            "exists": True,
            "client": {
                "id": process.get("id"),
                "name": process.get("client_name"),
                "number": process.get("process_number")
            }
        }
    
    return {"exists": False, "client": None}



async def run_get_clients_list(user: dict):
    """Obter lista de clientes para referência no upload."""
    clients = await db.processes.find(
        {},
        {"_id": 0, "id": 1, "client_name": 1, "process_number": 1}
    ).sort("client_name", 1).to_list(None)
    
    return {
        "total": len(clients),
        "clients": [
            {
                "id": c.get("id"),
                "name": c.get("client_name"),
                "number": c.get("process_number")
            }
            for c in clients
        ]
    }



async def run_diagnose_client_data(
    client_name: str,
    user: dict,
):
    """Diagnóstico de dados de um cliente."""
    process = await find_client_by_name(client_name)
    
    if not process:
        return {
            "found": False,
            "error": f"Cliente '{client_name}' não encontrado"
        }
    
    personal = process.get("personal_data", {})
    financial = process.get("financial_data", {})
    real_estate = process.get("real_estate_data", {})
    
    def count_filled(data: dict) -> Tuple[int, int, list]:
        """Conta campos preenchidos num dicionário de dados do processo.

        Um campo é considerado preenchido se não for None nem string vazia.

        Args:
            data: Dicionário (ex: personal_data, financial_data).

        Returns:
            Tuple[int, int, list]: (campos_preenchidos, total_campos,
                lista_de_chaves_preenchidas).
        """
        if not data:
            return 0, 0, []
        filled = [(k, v) for k, v in data.items() if v is not None and v != ""]
        return len(filled), len(data), [k for k, _ in filled]
    
    personal_filled, personal_total, personal_fields = count_filled(personal)
    financial_filled, financial_total, financial_fields = count_filled(financial)
    real_estate_filled, real_estate_total, real_estate_fields = count_filled(real_estate)
    
    co_buyers = process.get("co_buyers", [])
    co_applicants = process.get("co_applicants", [])
    
    result = {
        "found": True,
        "client_name": process.get("client_name"),
        "process_id": process.get("id"),
        "summary": {
            "personal_data": f"{personal_filled}/{personal_total} campos",
            "financial_data": f"{financial_filled}/{financial_total} campos",
            "real_estate_data": f"{real_estate_filled}/{real_estate_total} campos",
        },
        "filled_fields": {
            "personal": personal_fields,
            "financial": financial_fields,
            "real_estate": real_estate_fields,
        },
        "raw_data": {
            "email": process.get("client_email"),
            "phone": process.get("client_phone"),
            "personal_data": personal,
            "financial_data": financial,
        },
        "analyzed_documents": process.get("analyzed_documents", [])
    }
    
    if co_buyers:
        result["co_buyers"] = co_buyers
        result["summary"]["co_buyers"] = f"{len(co_buyers)} pessoa(s)"
    
    if co_applicants:
        result["co_applicants"] = co_applicants
        result["summary"]["co_applicants"] = f"{len(co_applicants)} pessoa(s)"
    
    return result



async def run_get_analyzed_documents(
    process_id: str,
    user: dict,
):
    """Listar documentos já analisados para um processo."""
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "client_name": 1, "analyzed_documents": 1}
    )
    
    if not process:
        return {"found": False, "error": "Processo não encontrado"}
    
    analyzed_docs = process.get("analyzed_documents", [])
    
    by_type = {}
    for doc in analyzed_docs:
        doc_type = doc.get("document_type", "outro")
        if doc_type not in by_type:
            by_type[doc_type] = []
        by_type[doc_type].append({
            "filename": doc.get("filename"),
            "analyzed_at": doc.get("analyzed_at"),
            "mes_referencia": doc.get("mes_referencia"),
            "fields_extracted": len(doc.get("fields_extracted", []))
        })
    
    return {
        "found": True,
        "client_name": process.get("client_name"),
        "total_documents": len(analyzed_docs),
        "by_type": by_type
    }


# ====================================================================
# ENDPOINTS DE CACHE
# ====================================================================
