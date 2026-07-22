"""Company list / get handlers.

Extraído de `routes/companies_crud.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from database import db
from models.company import CompanyListResponse, CompanyResponse
from services.companies_crud_api_helpers import resolve_logo_url


async def run_list_companies(search: Optional[str] = None):
    """Lista todas as empresas configuradas no sistema."""
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"nif": {"$regex": search, "$options": "i"}},
        ]

    companies = await db.companies.find(
        query, {"_id": 0}
    ).sort("name", 1).to_list(200)

    result = []
    for c in companies:
        total_users = await db.users.count_documents({
            "company": c.get("name", ""),
        })
        doc = {**c, "total_users": total_users}
        doc["logo_url"] = resolve_logo_url(doc.get("logo_url"))
        result.append(CompanyResponse(**doc).model_dump())

    return CompanyListResponse(companies=result, total=len(result))


async def run_list_available_companies():
    """Lista nomes das empresas disponíveis (para selects/dropdowns)."""
    cursor = db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1}
    ).sort("name", 1)
    return await cursor.to_list(200)


async def run_get_company(company_id: str):
    """Obtém uma empresa pelo ID (ou por nome como fallback)."""
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        company = await db.companies.find_one({"name": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    if not company.get("id"):
        company["id"] = company.get("name", company_id)
    if not company.get("name"):
        company["name"] = company_id
    company.setdefault("email_sync_enabled", False)
    company.setdefault("total_users", 0)

    total_users = await db.users.count_documents({
        "company": company.get("name", ""),
    })
    company["total_users"] = total_users
    company["logo_url"] = resolve_logo_url(company.get("logo_url"))
    return CompanyResponse(**company)
