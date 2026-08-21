"""User-company-role CRUD handlers.

Extraído de `routes/user_company_roles.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from models.user_company_role import (
    UserCompanyRoleCreate,
    UserCompanyRoleUpdate,
    UserRoleAssignBody,
)

logger = logging.getLogger(__name__)

LAST_UCR_DELETE_DETAIL = (
    "Não é possível remover o único acesso deste utilizador. "
    "Um utilizador tem de ter pelo menos um acesso UCR."
)


def _normalize_ucr_doc(doc: dict) -> dict:
    """Garante keys estáveis para o frontend (id, company_name, role/role_name)."""
    if not doc:
        return doc
    out = dict(doc)
    raw_id = out.get("id") or out.get("_id")
    out.pop("_id", None)
    if raw_id is not None:
        out["id"] = str(raw_id)

    company_id = (
        out.get("company_id")
        or out.get("companyId")
        or out.get("company")
    )
    company_name = (
        out.get("company_name")
        or out.get("companyName")
        or (out.get("company") if isinstance(out.get("company"), str) else None)
        or company_id
    )
    role = out.get("role") or out.get("role_name") or out.get("roleName")
    if company_id:
        out["company_id"] = str(company_id)
    if company_name:
        out["company_name"] = str(company_name).strip()
    if role:
        out["role"] = role
        out["role_name"] = role
    return out


async def run_list_user_company_roles(
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
):
    """Lista associações user-company-role."""
    query = {}
    if user_id:
        query["user_id"] = user_id
    if company_id:
        query["company_id"] = company_id

    roles = await db.user_company_roles.find(query).sort(
        "company_name", 1
    ).to_list(500)

    normalized = [_normalize_ucr_doc(role) for role in roles]
    return {"roles": normalized, "total": len(normalized)}


async def _find_ucr_by_id(role_id: str):
    """Resolve UCR por `id` UUID ou, em docs legados, por `_id` Mongo."""
    existing = await db.user_company_roles.find_one({"id": role_id})
    if existing:
        return existing
    try:
        from bson import ObjectId
        from bson.errors import InvalidId
    except ImportError:
        return None
    try:
        existing = await db.user_company_roles.find_one({"_id": ObjectId(role_id)})
        if existing:
            return existing
    except (InvalidId, TypeError, ValueError):
        return None
    return None


async def run_get_user_company_role(role_id: str):
    """Obtém uma associação específica pelo ID."""
    role = await _find_ucr_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Associação não encontrada")
    return _normalize_ucr_doc(role)


async def run_create_user_company_role(payload: UserCompanyRoleCreate):
    """Associa um utilizador a uma empresa com um role específico."""
    user = await db.users.find_one(
        {"id": payload.user_id}, {"_id": 0, "id": 1, "name": 1}
    )
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    existing = await db.user_company_roles.find_one({
        "user_id": payload.user_id,
        "company_id": payload.company_id,
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Utilizador já está associado a esta empresa com role "
                f"'{existing.get('role')}'"
            ),
        )

    role_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": role_id,
        "user_id": payload.user_id,
        "company_id": payload.company_id,
        "company_name": payload.company_name,
        "role": payload.role,
        "is_default": payload.is_default,
        "signature": payload.signature,
        "professional_phone": payload.professional_phone,
        "job_title": payload.job_title,
        "created_at": now,
        "updated_at": now,
    }

    if payload.is_default:
        await db.user_company_roles.update_many(
            {"user_id": payload.user_id, "is_default": True},
            {"$set": {"is_default": False, "updated_at": now}},
        )

    await db.user_company_roles.insert_one(doc)
    doc.pop("_id", None)

    logger.info(
        f"[UserCompanyRole] Associação criada: user={payload.user_id} "
        f"company='{payload.company_name}' role={payload.role} "
        f"default={payload.is_default}"
    )

    return {"success": True, "id": role_id}


async def run_update_user_company_role(
    role_id: str, payload: UserCompanyRoleUpdate,
):
    """Atualiza o role ou is_default de uma associação existente."""
    existing = await db.user_company_roles.find_one({"id": role_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Associação não encontrada")

    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}

    if payload.role is not None:
        update_data["role"] = payload.role

    if payload.is_default is not None:
        if payload.is_default:
            await db.user_company_roles.update_many(
                {
                    "user_id": existing["user_id"],
                    "is_default": True,
                    "id": {"$ne": role_id},
                },
                {"$set": {"is_default": False, "updated_at": now}},
            )
        update_data["is_default"] = payload.is_default

    if payload.signature is not None:
        update_data["signature"] = payload.signature
    if payload.professional_phone is not None:
        update_data["professional_phone"] = payload.professional_phone
    if payload.job_title is not None:
        update_data["job_title"] = payload.job_title

    await db.user_company_roles.update_one(
        {"id": role_id},
        {"$set": update_data},
    )

    logger.info(
        f"[UserCompanyRole] Associação atualizada: id={role_id} "
        f"changes={list(update_data.keys())}"
    )

    return {"success": True, "message": "Associação atualizada"}


async def run_delete_user_company_role(role_id: str):
    """Remove uma associação user-company-role.

    Recusa deixar o utilizador sem nenhum acesso UCR (último vínculo).
    """
    existing = await _find_ucr_by_id(role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Associação não encontrada")

    remaining = await db.user_company_roles.count_documents(
        {"user_id": existing["user_id"]}
    )
    if remaining <= 1:
        raise HTTPException(status_code=400, detail=LAST_UCR_DELETE_DETAIL)

    if existing.get("id"):
        await db.user_company_roles.delete_one({"id": existing["id"]})
    else:
        await db.user_company_roles.delete_one({"_id": existing["_id"]})

    logger.info(
        f"[UserCompanyRole] Associação removida: id={role_id} "
        f"user={existing['user_id']} company='{existing.get('company_name')}'"
    )

    return {"success": True, "message": "Associação removida"}


async def run_assign_user_company_role(user_id: str, payload: UserRoleAssignBody):
    """Associa um acesso (empresa + cargo) a um utilizador.

    Conveniência para POST /admin/users/{user_id}/roles — resolve o nome da
    empresa se não vier no payload e reutiliza o create canónico.
    """
    company = await db.companies.find_one({"id": payload.company_id})
    if not company:
        company = await db.companies.find_one({"name": payload.company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    company_id = company.get("id") or payload.company_id
    company_name = (payload.company_name or company.get("name") or "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="Nome da empresa é obrigatório")

    existing_count = await db.user_company_roles.count_documents({"user_id": user_id})
    is_default = payload.is_default or existing_count == 0

    create_payload = UserCompanyRoleCreate(
        user_id=user_id,
        company_id=company_id,
        company_name=company_name,
        role=payload.role,
        is_default=is_default,
    )
    return await run_create_user_company_role(create_payload)
