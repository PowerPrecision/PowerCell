"""Permissões e capabilities (admin).

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from services.admin_helpers import _safe_float, _audit_log
from services.permissions import (
    get_default_permissions_for_role,
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE,
    get_user_capabilities,
    build_permissions_document,
)
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
)

logger = logging.getLogger(__name__)

class CapabilityUpdateRequest(BaseModel):
    capabilities: dict  # { "PROCESS_DELETE": true, "FINANCE_VIEW": false }



async def run_get_available_permissions(user: dict):
    """
    Retorna todas as permissões disponíveis no sistema.
    Usado pelo frontend para exibir opções de permissões.
    """
    return {
        "success": True,
        "data": get_all_available_permissions()
    }


async def run_get_default_permissions(user: dict):
    """
    Retorna as permissões padrão para cada role.
    Usado pelo frontend para mostrar permissões quando muda o role.
    """
    return {
        "success": True,
        "roles": get_role_display_info(),
        "defaults": DEFAULT_PERMISSIONS_BY_ROLE
    }


async def run_get_default_permissions_for_role(role: str, user: dict):
    """Retorna as permissões padrão para um role específico.

    Usado pelo frontend para pré-preencher as permissões quando o
    admin seleciona um role ao criar ou editar um utilizador.

    Args:
        role: Nome do role (ex: "consultor", "admin").
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: success, role, permissions (lista de chaves).

    Raises:
        HTTPException(400): Se role não existir no mapeamento.
    """
    if role not in DEFAULT_PERMISSIONS_BY_ROLE:
        raise HTTPException(status_code=400, detail="Role inválido")
    
    return {
        "success": True,
        "role": role,
        "permissions": get_default_permissions_for_role(role)
    }


async def run_reset_user_permissions(user_id: str, user: dict):
    """Redefine as permissões de um utilizador para o padrão do seu role.

    Útil quando um utilizador tem permissões personalizadas incorretas
    e o admin quer restaurar os valores por defeito do role.

    Args:
        user_id: ID do utilizador cujas permissões serão redefinidas.
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: success, message, permissions (nova lista de permissões).

    Raises:
        HTTPException(404): Se utilizador não encontrado.
    """
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    role = target_user.get("role")
    perms_doc = build_permissions_document(role)
    
    await db.users.update_one(
        {"id": user_id}, 
        {"$set": {"permissions": perms_doc}}
    )
    
    await _audit_log(
        "permissions_reset", 
        "user", 
        user_id, 
        user, 
        {"role": role, "permissions": perms_doc}
    )
    
    return {
        "success": True,
        "message": f"Permissões redefinidas para o padrão do role '{role}'",
        "permissions": perms_doc
    }


async def run_get_capabilities_registry(user: dict):
    """
    Retorna o registo completo de capabilities, categorias e defaults por cargo.
    Usado pelo PermissionsTab para construir a matrix de permissões.
    """
    return {
        "success": True,
        "capabilities": get_all_capabilities(),
        "categories": CATEGORIES,
        "role_defaults": {role: defaults for role, defaults in ROLE_CAPABILITY_DEFAULTS.items() 
                         if role not in ["cliente"]},
        "super_admin_roles": SUPER_ADMIN_ROLES,
    }


async def run_get_capabilities_grouped(user: dict):
    """Retorna capabilities agrupadas por categoria (para rendering da matrix)."""
    return {
        "success": True,
        "categories": CATEGORIES,
        "capabilities_by_category": get_capabilities_by_category(),
        "role_defaults": {role: defaults for role, defaults in ROLE_CAPABILITY_DEFAULTS.items() 
                         if role not in ["cliente"]},
        "super_admin_roles": SUPER_ADMIN_ROLES,
    }


async def run_update_role_defaults(role: str, request: CapabilityUpdateRequest, user: dict):
    """
    Atualiza os defaults de capabilities para um cargo.
    Isto afecta TODOS os utilizadores com esse cargo que NÃO têm overrides.
    Apenas admin pode alterar defaults (CEO pode visualizar mas não alterar).
    """
    if user.get("role") != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas o Admin pode alterar defaults de cargo")
    
    if role in SUPER_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="Não é possível alterar permissões de admin/CEO (Super Admin Bypass)")
    
    if role not in ROLE_CAPABILITY_DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Cargo '{role}' não encontrado")
    
    # Validar capabilities
    validated = validate_capabilities(request.capabilities)
    
    # Atualizar defaults em memória (para a sessão actual)
    ROLE_CAPABILITY_DEFAULTS[role].update(validated)
    
    # Persistir na collection system_config para sobreviver a restarts
    await db.system_config.update_one(
        {"key": "role_capability_defaults"},
        {"$set": {"key": "role_capability_defaults", "value": {r: d for r, d in ROLE_CAPABILITY_DEFAULTS.items()}}},
        upsert=True
    )
    
    await _audit_log(
        "role_defaults_updated",
        "role",
        role,
        user,
        {"updated_capabilities": validated}
    )
    
    return {
        "success": True,
        "message": f"Defaults do cargo '{role}' atualizados",
        "role": role,
        "capabilities": ROLE_CAPABILITY_DEFAULTS[role],
    }


async def run_get_user_permissions(user_id: str, user: dict):
    """
    Retorna as capabilities efetivas de um utilizador específico,
    incluindo role defaults + overrides pessoais.
    """
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    effective_caps = get_user_capabilities(target)
    role_defaults = get_role_defaults(target.get("role", ""))
    overrides = (target.get("permissions") or {}).get("capabilities") or {}
    
    return {
        "success": True,
        "user_id": user_id,
        "name": target.get("name"),
        "role": target.get("role"),
        "effective_capabilities": effective_caps,
        "role_defaults": role_defaults,
        "overrides": overrides,
    }


async def run_update_user_permissions(user_id: str, request: CapabilityUpdateRequest, user: dict):
    """
    Atualiza as capabilities (overrides) de um utilizador específico.
    Apenas as capabilities enviadas são alteradas; as restantes mantêm-se.
    """
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    target_role = target.get("role", "")
    
    # Não permitir alterar permissões de Super Admin
    if target_role in SUPER_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="Não é possível alterar permissões de admin/CEO (Super Admin Bypass)")
    
    # Validar capabilities
    validated = validate_capabilities(request.capabilities)
    
    # Obter overrides actuais e mesclar
    current_perms = target.get("permissions") or {}
    current_caps = current_perms.get("capabilities") or {}
    current_caps.update(validated)
    
    # Construir documento de permissões completo
    perms_doc = build_permissions_document(target_role, current_caps)
    
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"permissions": perms_doc}}
    )
    
    await _audit_log(
        "user_permissions_updated",
        "user",
        user_id,
        user,
        {"updated_capabilities": validated, "full_permissions": perms_doc}
    )
    
    return {
        "success": True,
        "message": f"Permissões de '{target.get('name')}' atualizadas",
        "user_id": user_id,
        "capabilities": perms_doc.get("capabilities", {}),
    }


