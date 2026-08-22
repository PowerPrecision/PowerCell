"""Set-active-company handler.

Extraído de `routes/user_company_roles.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def run_set_active_company(data: dict, user: dict):
    """Define o UCR ativo (empresa + cargo) para o utilizador autenticado.

    Pacote FH / C6: a chave única é ``{user_id, company_id, role}`` — o mesmo
    utilizador pode ter vários cargos na mesma empresa, por isso ``is_default``
    tem de ser aplicado à combinação exacta, não só a user+company.
    """
    company_id = data.get("company_id")
    role = (data.get("role") or "").strip().lower()
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id é obrigatório")
    if not role:
        raise HTTPException(status_code=400, detail="role é obrigatório")

    association = await db.user_company_roles.find_one({
        "user_id": user["id"],
        "company_id": company_id,
        "role": role,
    })

    if not association:
        raise HTTPException(
            status_code=403,
            detail="Não tem acesso a esta empresa com este cargo",
        )

    now = datetime.now(timezone.utc).isoformat()

    await db.user_company_roles.update_many(
        {"user_id": user["id"], "is_default": True},
        {"$set": {"is_default": False, "updated_at": now}},
    )

    await db.user_company_roles.update_one(
        {"user_id": user["id"], "company_id": company_id, "role": role},
        {"$set": {"is_default": True, "updated_at": now}},
    )

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "company": association["company_name"],
            "updated_at": now,
        }},
    )

    logger.info(
        f"[UserCompanyRole] Empresa ativa alterada: user={user['id']} "
        f"company='{association['company_name']}'"
    )

    return {
        "success": True,
        "active_company_id": company_id,
        "active_company_name": association["company_name"],
        "active_company_role": association["role"],
    }
