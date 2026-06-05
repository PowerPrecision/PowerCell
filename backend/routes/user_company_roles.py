"""
====================================================================
ROTAS: UserCompanyRole — Associação Muitos-para-Muitos
====================================================================
CRUD para gerir as associações entre utilizadores e empresas com roles.

Um utilizador pode pertencer a várias empresas com papéis diferentes.
A associação com is_default=True define a empresa que carrega no login.

PREFIX: /admin/user-company-roles

MIGRAÇÃO:
  POST /admin/user-company-roles/migrate — popula a coleção a partir
  do campo `company` existente nos documentos dos utilizadores.
====================================================================
"""

import uuid
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from models.user_company_role import (
    UserCompanyRoleCreate,
    UserCompanyRoleUpdate,
    UserCompanyRoleResponse,
)
from services.auth import require_admin, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/user-company-roles",
    tags=["User Company Roles"],
    dependencies=[Depends(require_admin())]
)


# ====================================================================
# LIST — Todas as associações (com filtros)
# ====================================================================

@router.get("")
async def list_user_company_roles(
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
):
    """
    Lista associações user-company-role.
    Filtra por user_id e/ou company_id se fornecidos.
    """
    query = {}
    if user_id:
        query["user_id"] = user_id
    if company_id:
        query["company_id"] = company_id

    roles = await db.user_company_roles.find(
        query, {"_id": 0}
    ).sort("company_name", 1).to_list(500)

    return {"roles": roles, "total": len(roles)}


# ====================================================================
# GET by ID
# ====================================================================

@router.get("/{role_id}")
async def get_user_company_role(role_id: str):
    """Obtém uma associação específica pelo ID."""
    role = await db.user_company_roles.find_one(
        {"id": role_id}, {"_id": 0}
    )
    if not role:
        raise HTTPException(status_code=404, detail="Associação não encontrada")
    return role


# ====================================================================
# CREATE — Associar utilizador a empresa
# ====================================================================

@router.post("")
async def create_user_company_role(payload: UserCompanyRoleCreate):
    """
    Associa um utilizador a uma empresa com um role específico.

    Se is_default=True, remove is_default das outras associações do mesmo user.
    """
    # Verificar se o utilizador existe
    user = await db.users.find_one({"id": payload.user_id}, {"_id": 0, "id": 1, "name": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # Verificar se a associação já existe
    existing = await db.user_company_roles.find_one({
        "user_id": payload.user_id,
        "company_id": payload.company_id,
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Utilizador já está associado a esta empresa com role '{existing.get('role')}'"
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
        "created_at": now,
        "updated_at": now,
    }

    # Se is_default=True, remover is_default das outras
    if payload.is_default:
        await db.user_company_roles.update_many(
            {"user_id": payload.user_id, "is_default": True},
            {"$set": {"is_default": False, "updated_at": now}}
        )

    await db.user_company_roles.insert_one(doc)

    logger.info(
        f"[UserCompanyRole] Associação criada: user={payload.user_id} "
        f"company='{payload.company_name}' role={payload.role} default={payload.is_default}"
    )

    return {"success": True, "id": role_id}


# ====================================================================
# UPDATE — Atualizar role ou is_default
# ====================================================================

@router.put("/{role_id}")
async def update_user_company_role(role_id: str, payload: UserCompanyRoleUpdate):
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
            # Remover is_default das outras associações deste user
            await db.user_company_roles.update_many(
                {"user_id": existing["user_id"], "is_default": True, "id": {"$ne": role_id}},
                {"$set": {"is_default": False, "updated_at": now}}
            )
        update_data["is_default"] = payload.is_default

    await db.user_company_roles.update_one(
        {"id": role_id},
        {"$set": update_data}
    )

    logger.info(
        f"[UserCompanyRole] Associação atualizada: id={role_id} "
        f"changes={list(update_data.keys())}"
    )

    return {"success": True, "message": "Associação atualizada"}


# ====================================================================
# DELETE — Remover associação
# ====================================================================

@router.delete("/{role_id}")
async def delete_user_company_role(role_id: str):
    """Remove uma associação user-company-role."""
    existing = await db.user_company_roles.find_one({"id": role_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Associação não encontrada")

    await db.user_company_roles.delete_one({"id": role_id})

    logger.info(
        f"[UserCompanyRole] Associação removida: id={role_id} "
        f"user={existing['user_id']} company='{existing.get('company_name')}'"
    )

    return {"success": True, "message": "Associação removida"}


# ====================================================================
# MIGRATE — Popular user_company_roles a partir do campo `company`
# ====================================================================

@router.post("/migrate")
async def migrate_company_field():
    """
    Migração: cria registos em user_company_roles a partir do campo
    `company` existente nos documentos dos utilizadores.

    Para cada utilizador com campo `company` preenchido:
      - Cria um registo user_company_roles com is_default=True
      - O company_id é o company_name (string) para backward compat
    """
    users = await db.users.find(
        {"company": {"$exists": True, "$nin": ["", None]}},
        {"_id": 0, "id": 1, "name": 1, "company": 1, "role": 1}
    ).to_list(500)

    created = 0
    skipped = 0
    errors = 0
    now = datetime.now(timezone.utc).isoformat()

    for user in users:
        user_id = user["id"]
        company_name = user["company"]
        user_role = user.get("role", "consultor")

        # Verificar se já existe associação
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
                "company_id": company_name,  # Usa company_name como ID
                "company_name": company_name,
                "role": user_role,
                "is_default": True,  # Primeira associação = default
                "created_at": now,
                "updated_at": now,
            }
            await db.user_company_roles.insert_one(doc)
            created += 1
        except Exception as e:
            logger.error(f"[UserCompanyRole] Erro na migração user={user_id}: {e}")
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


# ====================================================================
# SET ACTIVE COMPANY — Endpoint para o utilizador trocar de empresa
# ====================================================================

@router.post("/set-active-company")
async def set_active_company(
    data: dict,
    user: dict = Depends(get_current_user),
):
    """
    Define a empresa ativa para o utilizador autenticado.

    Recebe: { "company_id": "Power Real Estate" }
    Valida que o utilizador tem acesso a essa empresa.
    Atualiza is_default na associação.

    O frontend deve enviar o header X-Company-Id em todos os pedidos
    subsequentes para que o backend resolva o contexto correto.
    """
    company_id = data.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id é obrigatório")

    # Verificar que o utilizador tem acesso a esta empresa
    association = await db.user_company_roles.find_one({
        "user_id": user["id"],
        "company_id": company_id,
    })

    if not association:
        raise HTTPException(
            status_code=403,
            detail="Não tem acesso a esta empresa"
        )

    now = datetime.now(timezone.utc).isoformat()

    # Remover is_default das outras
    await db.user_company_roles.update_many(
        {"user_id": user["id"], "is_default": True},
        {"$set": {"is_default": False, "updated_at": now}}
    )

    # Definir a nova como default
    await db.user_company_roles.update_one(
        {"user_id": user["id"], "company_id": company_id},
        {"$set": {"is_default": True, "updated_at": now}}
    )

    # Atualizar o campo `company` no user document (backward compat)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"company": association["company_name"], "updated_at": now}}
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


# ====================================================================
# MIGRATE EMAIL CONFIGS — Popular user_email_configs a partir do embebido
# ====================================================================

@router.post("/migrate-email-configs")
async def migrate_email_configs():
    """
    Migração: move as configs de email embebidas nos documentos dos
    utilizadores para a coleção user_email_configs.

    A coleção user_email_configs tem índice único em (user_id, company_id),
    garantindo que cada utilizador só tem UMA config de email por empresa.

    Esta migração é segura de correr múltiplas vezes — configs já
    existentes são ignoradas (skipped).
    """
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
