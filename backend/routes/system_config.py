"""
====================================================================
ROTAS PARA CONFIGURAÇÕES DO SISTEMA — thin stubs
====================================================================
Logic in services/system_config_*.py.
Do NOT overwrite services/system_config.py (core load/save/cache —
see AGENTS.md). Use system_config_api / _connections / _admin_ops /
_system_emails instead.
====================================================================
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Query, Request

from services.auth import get_current_user, require_roles
from models.auth import UserRole

from services.system_config_scope import (
    carregar_ambito_de_configuracao,
    listar_empresas_configuraveis,
    resolver_configuracao_global,
    resolver_empresa_para_leitura,
    resolver_empresa_pedida,
)
from services.system_config_api import (
    run_get_config,
    run_get_excel_export_permission,
    run_get_config_fields,
    run_get_available_companies,
    run_update_config,
)
from services.system_config_connections import run_test_service_connection
from services.system_config_admin_ops import (
    run_complete_setup,
    run_get_storage_info,
    run_reset_cache,
    run_reveal_secrets,
)
from services.system_config_system_emails import (
    SystemEmailConfigCreate,
    SystemEmailConfigUpdate,
    run_list_system_email_configs,
    run_get_system_email_config,
    run_create_system_email_config,
    run_update_system_email_config,
    run_delete_system_email_config,
    run_test_system_email_config,
)

router = APIRouter(prefix="/system-config", tags=["System Configuration"])


@router.get("")
async def get_config(
    request: Request,
    company_id: Optional[str] = Query("default", description="ID da empresa (default = global)"),
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obter todas as configurações do sistema.
    Apenas admin e CEO podem aceder.

    MULTI-EMPRESA: Use o parâmetro company_id para obter a config de uma empresa específica.
    Se não for fornecido, retorna a config global (retrocompatível).

    ÂMBITO: ver `services/system_config_scope.py` (ADMIN todas; CEO as dele).
    """
    company_id = await resolver_empresa_pedida(user, request, company_id)
    return await run_get_config(company_id=company_id)


@router.get("/public/export-permission")
async def get_excel_export_permission(
    request: Request,
    company_id: Optional[str] = Query("default", description="ID da empresa"),
    user: dict = Depends(get_current_user),
):
    """
    Verificar se a exportação para Excel está permitida.
    Endpoint público (qualquer utilizador autenticado) — usado pelo frontend
    para mostrar/ocultar os botões de exportação.

    Empresa alheia → 404 (senão cada id inventado criava um documento).
    """
    company_id = await resolver_empresa_para_leitura(user, request, company_id)
    return await run_get_excel_export_permission(company_id=company_id)


@router.get("/fields")
async def get_config_fields(user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))):
    """
    Obter definição dos campos de configuração.
    Útil para o frontend construir os formulários.
    """
    return await run_get_config_fields()


@router.get("/companies")
async def get_available_companies(request: Request, user: dict = Depends(get_current_user)):
    """
    Listar empresas com configuração própria no sistema.

    MULTI-EMPRESA: Retorna a lista de company_ids disponíveis para o dropdown
    no frontend (Definições Gerais + ProfilePage). Leitura permitida para
    todos os utilizadores autenticados — apenas a escrita requer ADMIN/CEO.

    ÂMBITO: cada um vê só as empresas que pode usar (ADMIN todas).
    """
    ambito = await carregar_ambito_de_configuracao(user, request)
    return await run_get_available_companies(
        await listar_empresas_configuraveis(ambito)
    )


@router.patch("/{section}")
async def update_config(
    section: str,
    data: Dict[str, Any],
    request: Request,
    company_id: Optional[str] = Query("default", description="ID da empresa (default = global)"),
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))
):
    """
    Actualizar uma secção da configuração.

    MULTI-EMPRESA: Use o parâmetro company_id para actualizar a config de uma empresa específica.
    A validação do `company_id` vem ANTES de qualquer escrita (ver `get_config`).
    """
    company_id = await resolver_empresa_pedida(user, request, company_id)
    return await run_update_config(section=section, data=data, company_id=company_id, user=user)


@router.post("/test-connection/{service}")
async def test_service_connection(
    service: str,
    request: Request,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """
    Testar ligação a um serviço (email, storage, etc.).
    Testa a configuração GLOBAL: só o ADMIN.
    """
    await resolver_configuracao_global(user, request)
    return await run_test_service_connection(service=service)


@router.post("/complete-setup")
async def complete_setup(request: Request, user: dict = Depends(require_roles([UserRole.MASTER]))):
    """
    Marcar a configuração inicial como concluída (global).
    """
    await resolver_configuracao_global(user, request)
    return await run_complete_setup()


@router.get("/storage-info")
async def get_storage_info(user: dict = Depends(get_current_user)):
    """
    Obter informação sobre o sistema de armazenamento configurado.
    Disponível para todos os utilizadores autenticados.

    Retorna:
    - provider: Tipo de storage (aws_s3, google_drive, onedrive, dropbox, none)
    - provider_label: Nome amigável do provider
    - configured: Se está configurado correctamente
    - base_url: URL base para aceder aos ficheiros (se aplicável)
    """
    return await run_get_storage_info()


@router.post("/reset-cache")
async def reset_cache(user: dict = Depends(require_roles([UserRole.MASTER]))):
    """
    Forçar recarga das configurações do sistema.
    """
    return await run_reset_cache()


@router.get("/reveal-secrets")
async def reveal_secrets(
    request: Request,
    section: Optional[str] = Query(None, description="Secção a revelar (email, ai, storage, credit_services)"),
    company_id: Optional[str] = Query("default", description="ID da empresa (default = global)"),
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]))
):
    """
    Revelar valores sensíveis (passwords, API keys) de uma secção de configuração.
    Só da empresa (ou global) que pertence ao utilizador.
    """
    company_id = await resolver_empresa_pedida(user, request, company_id)
    return await run_reveal_secrets(section=section, company_id=company_id)


# =====================================================================
# SYSTEM EMAIL CONFIGS — CRUD para emails do sistema (DOCUMENTS, RGPD, etc.)
# =====================================================================

@router.get("/system-emails")
async def list_system_email_configs(request: Request, user: dict = Depends(require_roles([UserRole.MASTER]))):
    """
    Listar todas as configurações de email do sistema.
    Passwords são substituídas por has_password: true/false.
    São globais: só quem possui a infra partilhada.
    """
    await resolver_configuracao_global(user, request)
    return await run_list_system_email_configs()


@router.get("/system-emails/{purpose}")
async def get_system_email_config(
    purpose: str,
    request: Request,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """
    Obter configuração de email do sistema por propósito.
    """
    await resolver_configuracao_global(user, request)
    return await run_get_system_email_config(purpose=purpose)


@router.post("/system-emails")
async def create_system_email_config(
    payload: SystemEmailConfigCreate,
    request: Request,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """
    Criar nova configuração de email do sistema.
    A password é encriptada antes de guardar.
    """
    await resolver_configuracao_global(user, request)
    return await run_create_system_email_config(payload=payload, user=user)


@router.put("/system-emails/{purpose}")
async def update_system_email_config(
    purpose: str,
    payload: SystemEmailConfigUpdate,
    request: Request,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """
    Actualizar configuração de email do sistema.
    Se password for enviada, é encriptada; se vazia, mantém a existente.
    """
    await resolver_configuracao_global(user, request)
    return await run_update_system_email_config(purpose=purpose, payload=payload, user=user)


@router.delete("/system-emails/{purpose}")
async def delete_system_email_config(
    purpose: str,
    request: Request,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """
    Eliminar configuração de email do sistema.
    """
    await resolver_configuracao_global(user, request)
    return await run_delete_system_email_config(purpose=purpose, user=user)


@router.post("/system-emails/{purpose}/test")
async def test_system_email_config(
    purpose: str,
    request: Request,
    user: dict = Depends(require_roles([UserRole.MASTER]))
):
    """
    Testar ligação SMTP para um propósito específico.
    """
    await resolver_configuracao_global(user, request)
    return await run_test_system_email_config(purpose=purpose)
