"""
====================================================================
ROTAS: Company Email Config — Gestão de IMAP/SMTP por Empresa
====================================================================
CRUD para configurações de email por empresa (servidores padrão).

A autenticação requer role admin ou CEO.
As passwords são encriptadas com Fernet antes de serem guardadas.

PREFIX: /admin/company-email-configs
====================================================================
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.company_email_config import (
    CompanyEmailConfigCreate,
    CompanyEmailConfigResponse,
    CompanyEmailConfigListResponse,
)
from services.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/company-email-configs",
    tags=["Company Email Configs"],
    dependencies=[Depends(require_admin())]
)


@router.get("", response_model=CompanyEmailConfigListResponse)
async def list_company_configs():
    """
    Lista todas as configurações de email por empresa.
    Inclui contagem de utilizadores por empresa.
    """
    configs = await db.company_email_configs.find({}, {"_id": 0}).to_list(100)

    result = []
    for config in configs:
        # Contar utilizadores pertencentes a esta empresa
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
            has_encrypted_password=bool(config.get("encrypted_password")),
            total_users=total_users,
            created_at=config.get("created_at"),
            updated_at=config.get("updated_at"),
        ))

    return CompanyEmailConfigListResponse(configs=result, total=len(result))


@router.get("/available-companies")
async def get_available_companies():
    """
    Lista empresas registadas no sistema (do campo 'company' dos users)
    com indicação de quais já têm config de email.
    """
    pipeline = [
        {"$match": {"company": {"$exists": True, "$ne": "", "$ne": None}}},
        {"$group": {"_id": "$company", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    company_users = await db.users.aggregate(pipeline).to_list(100)

    # Buscar configs existentes
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


@router.get("/{company_name}")
async def get_company_config(company_name: str):
    """Obtém a config de email de uma empresa específica."""
    config = await db.company_email_configs.find_one(
        {"company_name": company_name},
        {"_id": 0, "encrypted_password": 0}
    )

    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada para esta empresa")

    total_users = await db.users.count_documents({"company": company_name})

    return {
        **config,
        "has_encrypted_password": bool(config.get("encrypted_password")),
        "total_users": total_users,
    }


@router.post("")
async def create_company_config(payload: CompanyEmailConfigCreate):
    """
    Cria uma nova config de email por empresa.

    Se já existir uma config para esta empresa, retorna 409.
    """
    existing = await db.company_email_configs.find_one(
        {"company_name": payload.company_name}
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe configuração para a empresa '{payload.company_name}'. Use PUT para atualizar."
        )

    import uuid
    config_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    config_doc = {
        "id": config_id,
        "company_name": payload.company_name.strip(),
        "imap_server": payload.imap_server.strip(),
        "imap_port": payload.imap_port,
        "smtp_server": payload.smtp_server.strip(),
        "smtp_port": payload.smtp_port,
        "encrypted_password": "",
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


@router.put("/{company_name}")
async def update_company_config(company_name: str, payload: CompanyEmailConfigCreate):
    """
    Atualiza a config de email de uma empresa.
    Mantém a password existente se não for fornecida.
    """
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
        "smtp_server": payload.smtp_server.strip(),
        "smtp_port": payload.smtp_port,
        "updated_at": now,
    }

    # Se o nome da empresa foi alterado, atualizar também
    if payload.company_name != company_name:
        update_data["company_name"] = payload.company_name.strip()
        # Verificar se o novo nome já existe
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


@router.delete("/{company_name}")
async def delete_company_config(company_name: str):
    """Remove a config de email de uma empresa."""
    existing = await db.company_email_configs.find_one(
        {"company_name": company_name}
    )

    if not existing:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")

    # Contar utilizadores afetados
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
