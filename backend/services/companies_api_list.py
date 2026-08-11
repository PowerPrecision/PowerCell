"""Company email config list / available handlers.

Extraído de `routes/companies.py`.
Use companies_api_* (not companies_crud_api_*).
"""
from __future__ import annotations

from database import db
from models.company_email_config import (
    CompanyEmailConfigResponse,
    CompanyEmailConfigListResponse,
)


async def run_list_company_configs():
    """Lista todas as configurações de email por empresa."""
    configs = await db.company_email_configs.find({}, {"_id": 0}).to_list(100)

    result = []
    for config in configs:
        total_users = await db.users.count_documents({
            "company": config.get("company_name", "")
        })

        result.append(CompanyEmailConfigResponse(
            id=config.get("id", ""),
            company_name=config.get("company_name", ""),
            imap_server=config.get("imap_server"),
            imap_port=config.get("imap_port", 993),
            smtp_server=config.get("smtp_server"),
            smtp_port=config.get("smtp_port", 465),
            require_ssl=config.get("require_ssl", True),
            has_encrypted_password=bool(config.get("encrypted_password")),
            total_users=total_users,
            created_at=config.get("created_at"),
            updated_at=config.get("updated_at"),
        ))

    return CompanyEmailConfigListResponse(configs=result, total=len(result))


async def run_get_available_companies():
    """Lista empresas registadas com indicação de config de email."""
    pipeline = [
        {"$match": {"company": {"$exists": True, "$nin": ["", None]}}},
        {"$group": {"_id": "$company", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    company_users = await db.users.aggregate(pipeline).to_list(100)

    existing_configs = await db.company_email_configs.find(
        {}, {"_id": 0, "company_name": 1}
    ).to_list(100)
    configured_companies = {c["company_name"] for c in existing_configs}

    result = []
    for item in company_users:
        name = item["_id"]
        result.append({
            "company_name": name,
            "total_users": item["total"],
            "has_email_config": name in configured_companies,
        })

    return {"companies": result, "total": len(result)}


async def run_get_company_config(company_name: str):
    """Obtém a config de email de uma empresa específica."""
    from fastapi import HTTPException

    config = await db.company_email_configs.find_one(
        {"company_name": company_name},
        {"_id": 0, "encrypted_password": 0}
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada para esta empresa")

    total_users = await db.users.count_documents({"company": company_name})

    return {
        **config,
        "require_ssl": config.get("require_ssl", True),
        "has_encrypted_password": bool(config.get("encrypted_password")),
        "total_users": total_users,
    }
