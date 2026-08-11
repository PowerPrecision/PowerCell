"""User-company-role migration handlers.

Extraído de `routes/user_company_roles.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)


async def run_migrate_company_field():
    """Cria registos UCR a partir do campo `company` nos utilizadores."""
    users = await db.users.find(
        {"company": {"$exists": True, "$nin": ["", None]}},
        {"_id": 0, "id": 1, "name": 1, "company": 1, "role": 1},
    ).to_list(500)

    created = 0
    skipped = 0
    errors = 0
    now = datetime.now(timezone.utc).isoformat()

    for user in users:
        user_id = user["id"]
        company_name = user["company"]
        user_role = user.get("role", "consultor")

        existing = await db.user_company_roles.find_one({
            "user_id": user_id,
            "company_id": company_name,
        })
        if existing:
            skipped += 1
            continue

        try:
            doc = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "company_id": company_name,
                "company_name": company_name,
                "role": user_role,
                "is_default": True,
                "created_at": now,
                "updated_at": now,
            }
            await db.user_company_roles.insert_one(doc)
            created += 1
        except Exception as e:
            logger.error(
                f"[UserCompanyRole] Erro na migração user={user_id}: {e}"
            )
            errors += 1

    logger.info(
        f"[UserCompanyRole] Migração concluída: {created} criados, "
        f"{skipped} já existiam, {errors} erros"
    )

    return {
        "success": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


async def run_migrate_email_configs():
    """Move configs de email embebidas para user_email_configs."""
    from services.user_email_config_service import migrate_embedded_to_collection

    result = await migrate_embedded_to_collection()

    logger.info(
        f"[UserCompanyRole] Migração de email configs: "
        f"{result['created']} criados, {result['skipped']} já existiam, "
        f"{result['errors']} erros"
    )

    return {
        "success": True,
        **result,
    }
