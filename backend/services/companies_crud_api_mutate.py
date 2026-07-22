"""Company create / update / delete handlers.

Extraído de `routes/companies_crud.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.company import CompanyCreate, CompanyResponse, CompanyUpdate

logger = logging.getLogger(__name__)


async def run_create_company(data: CompanyCreate):
    """Cria uma nova empresa."""
    existing = await db.companies.find_one({"name": data.name})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma empresa com o nome '{data.name}'",
        )

    now = datetime.now(timezone.utc).isoformat()
    company_id = str(uuid.uuid4())

    doc = {
        "id": company_id,
        "name": data.name,
        "nif": data.nif,
        "address": data.address,
        "phone": data.phone,
        "email": data.email,
        "website": data.website,
        "logo_url": data.logo_url,
        "email_sync_enabled": data.email_sync_enabled,
        "created_at": now,
        "updated_at": now,
    }

    await db.companies.insert_one(doc)
    logger.info(f"[COMPANIES] Empresa criada: {data.name} ({company_id})")

    return CompanyResponse(**doc)


async def run_update_company(company_id: str, data: CompanyUpdate):
    """Atualiza os dados de uma empresa."""
    existing = await db.companies.find_one({"id": company_id})
    if not existing:
        existing = await db.companies.find_one({"name": company_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = existing.get("id", company_id)

    if data.name and data.name != existing.get("name"):
        dup = await db.companies.find_one({"name": data.name})
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma empresa com o nome '{data.name}'",
            )
        old_name = existing.get("name")
        if old_name:
            await db.users.update_many(
                {"company": old_name},
                {"$set": {"company": data.name}},
            )
            logger.info(
                f"[COMPANIES] Nome da empresa '{old_name}' → '{data.name}' "
                f"atualizado em utilizadores"
            )

    update_fields = data.model_dump(exclude_unset=True)
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.companies.update_one(
        {"id": real_id},
        {"$set": update_fields},
    )

    updated = await db.companies.find_one({"id": real_id}, {"_id": 0})
    if not updated:
        updated = existing
        updated.update(update_fields)
    total_users = await db.users.count_documents({
        "company": updated.get("name", ""),
    })
    updated["total_users"] = total_users
    if not updated.get("id"):
        updated["id"] = real_id
    if not updated.get("name"):
        updated["name"] = company_id

    logger.info(f"[COMPANIES] Empresa atualizada: {real_id}")
    return CompanyResponse(**updated)


async def run_delete_company(company_id: str):
    """Remove uma empresa e gere utilizadores associados."""
    company = await db.companies.find_one({"id": company_id})
    if not company:
        company = await db.companies.find_one({"name": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = company.get("id", company_id)
    company_name = company.get("name", company_id)

    users_with_this_company = await db.users.find(
        {"company": company_name},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(1000)

    blocked_users = []
    reassigned_users = []

    for u in users_with_this_company:
        other_ucrs = await db.user_company_roles.find({
            "user_id": u["id"],
            "company_id": {"$ne": real_id},
        }).to_list(10)

        if other_ucrs:
            first_other = other_ucrs[0]
            new_company = first_other.get(
                "company_name", first_other.get("company_id", "default"),
            )
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {"company": new_company}},
            )
            reassigned_users.append({
                "id": u["id"],
                "name": u.get("name", ""),
                "new_company": new_company,
            })
        else:
            blocked_users.append({
                "id": u["id"],
                "name": u.get("name", ""),
                "email": u.get("email", ""),
            })

    if blocked_users:
        names = ", ".join(
            [f"{u['name']} ({u['email']})" for u in blocked_users[:5]]
        )
        suffix = (
            f" e mais {len(blocked_users)-5}" if len(blocked_users) > 5 else ""
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível eliminar: {len(blocked_users)} utilizador(es) "
                f"têm apenas esta empresa: {names}{suffix}. "
                f"Atribua outra empresa a estes utilizadores primeiro."
            ),
        )

    deleted_ucrs = await db.user_company_roles.delete_many(
        {"company_id": real_id}
    )

    await db.company_email_configs.delete_one({"company_name": company_name})
    await db.user_email_configs.delete_many({"company_id": real_id})

    await db.companies.delete_one({"id": real_id})

    logger.info(
        f"[COMPANIES] Empresa eliminada: {company_name} ({real_id}). "
        f"UCRs removidos: {deleted_ucrs.deleted_count}. "
        f"Users reatribuídos: {len(reassigned_users)}."
    )
    return {
        "detail": "Empresa eliminada com sucesso",
        "affected_users": len(reassigned_users),
        "reassigned_users": reassigned_users,
        "ucrs_removed": deleted_ucrs.deleted_count,
    }
