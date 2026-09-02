"""Company email config create / update / delete handlers.

Extraído de `routes/companies.py`.
Use companies_api_* (not companies_crud_api_*).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.company_email_config import CompanyEmailConfigCreate
from services.encryption import encryption_service

logger = logging.getLogger(__name__)


async def run_create_company_config(payload: CompanyEmailConfigCreate):
    """Cria uma nova config de email por empresa."""
    existing = await db.company_email_configs.find_one(
        {"company_name": payload.company_name}
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe configuração para a empresa '{payload.company_name}'. Use PUT para atualizar."
        )

    config_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    config_doc = {
        "id": config_id,
        "company_name": payload.company_name.strip(),
        "imap_server": payload.imap_server.strip(),
        "imap_port": payload.imap_port,
        "imap_user": payload.imap_user.strip(),
        "smtp_server": payload.smtp_server.strip(),
        "smtp_port": payload.smtp_port,
        "require_ssl": payload.require_ssl,
        "encrypted_password": encryption_service.encrypt(payload.imap_password) if payload.imap_password else "",
        "created_at": now,
        "updated_at": now,
    }

    await db.company_email_configs.insert_one(config_doc)

    logger.info(
        f"[CompanyEmailConfig] Config criada para empresa '{payload.company_name}' "
        f"(IMAP: {payload.imap_server}, SMTP: {payload.smtp_server})"
    )

    return {
        "success": True,
        "message": f"Configuração criada para '{payload.company_name}'",
        "id": config_id,
    }


async def run_update_company_config(company_name: str, payload: CompanyEmailConfigCreate):
    """Atualiza a config de email de uma empresa."""
    existing = await db.company_email_configs.find_one(
        {"company_name": company_name}
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Configuração não encontrada para '{company_name}'. Use POST para criar."
        )

    now = datetime.now(timezone.utc).isoformat()

    update_data = {
        "imap_server": payload.imap_server.strip(),
        "imap_port": payload.imap_port,
        "imap_user": payload.imap_user.strip(),
        "smtp_server": payload.smtp_server.strip(),
        "smtp_port": payload.smtp_port,
        "require_ssl": payload.require_ssl,
        "updated_at": now,
    }

    # Encriptar password se fornecida (não apaga a existente se vazio)
    if payload.imap_password:
        update_data["encrypted_password"] = encryption_service.encrypt(payload.imap_password)

    if payload.company_name != company_name:
        update_data["company_name"] = payload.company_name.strip()
        name_check = await db.company_email_configs.find_one(
            {"company_name": payload.company_name, "id": {"$ne": existing.get("id")}}
        )
        if name_check:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe configuração para '{payload.company_name}'"
            )

    await db.company_email_configs.update_one(
        {"company_name": company_name},
        {"$set": update_data}
    )

    logger.info(
        f"[CompanyEmailConfig] Config atualizada para '{company_name}' "
        f"(IMAP: {payload.imap_server}, SMTP: {payload.smtp_server})"
    )

    return {"success": True, "message": "Configuração atualizada"}


async def run_delete_company_config(company_name: str):
    """Remove a config de email de uma empresa."""
    existing = await db.company_email_configs.find_one(
        {"company_name": company_name}
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")

    total_users = await db.users.count_documents({"company": company_name})

    await db.company_email_configs.delete_one({"company_name": company_name})

    logger.info(
        f"[CompanyEmailConfig] Config removida para '{company_name}' "
        f"({total_users} utilizadores afetados)"
    )

    return {
        "success": True,
        "message": f"Configuração removida para '{company_name}'",
        "affected_users": total_users,
    }
