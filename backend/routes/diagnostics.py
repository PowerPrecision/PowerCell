"""
====================================================================
ROTAS DE DIAGNÓSTICO - SISTEMA
====================================================================
Endpoints para verificar o estado e configuração dos serviços.

Thin FastAPI stubs — logic in services/diagnostics_*.py.
====================================================================
"""

from fastapi import APIRouter, Depends

from models.auth import UserRole
from services.auth import require_roles, get_current_user

from services.diagnostics_helpers import SystemDiagnostics, TTLMigrationResponse
from services.diagnostics_system import (
    run_get_system_diagnostics,
    run_get_service_diagnostics,
    run_quick_system_check,
)
from services.diagnostics_security import (
    run_check_encryption_status,
    run_check_pii_compliance,
    run_test_openai_api_privacy,
)
from services.diagnostics_ttl import (
    run_migrate_ttl_datetime_fields,
    run_get_ttl_index_status,
)

router = APIRouter(prefix="/diagnostics", tags=["Diagnósticos"])


@router.get("", response_model=SystemDiagnostics)
async def get_system_diagnostics(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém diagnóstico completo do sistema.

    Retorna o estado de todos os serviços e últimos erros.
    """
    return await run_get_system_diagnostics()


@router.get("/service/{service_name}")
async def get_service_diagnostics(
    service_name: str,
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém diagnóstico detalhado de um serviço específico.
    """
    return await run_get_service_diagnostics(service_name)


@router.get("/quick-check")
async def quick_system_check(
    _current_user: dict = Depends(get_current_user)
):
    """
    Verificação rápida do sistema (para qualquer utilizador staff).

    Retorna apenas o resumo sem detalhes sensíveis.
    Ignora serviços desativados intencionalmente.
    """
    return await run_quick_system_check()


@router.get("/encryption")
async def check_encryption_status(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Verifica o estado do serviço de encriptação.

    Testa se a encriptação/desencriptação está a funcionar corretamente.
    """
    return await run_check_encryption_status()


@router.get("/pii-compliance")
async def check_pii_compliance(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Verifica a conformidade PII (Personally Identifiable Information) com a OpenAI.

    IMPORTANTE: Este endpoint verifica se os dados sensíveis dos clientes
    (NIFs, rendimentos, dados pessoais) estão protegidos de serem usados
    para treino de modelos públicos.

    Para garantir conformidade:
    1. Configure OPENAI_DATA_TRAINING_OPT_OUT=true nas variáveis de ambiente
    2. Verifique em https://platform.openai.com/account/organization que
       "Improve our models with your data" está DESATIVADO
    3. Configure OPENAI_ORGANIZATION_ID com o ID da sua organização corporativa

    Retorna:
    - Estado de conformidade
    - Verificações realizadas
    - Avisos e recomendações
    """
    return await run_check_pii_compliance()


@router.post("/pii-compliance/test-api")
async def test_openai_api_privacy(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Testa a conectividade com a API OpenAI verificando configurações de privacidade.

    Este endpoint faz uma chamada de teste à API para verificar:
    - Se a conectividade está funcional
    - Se o Organization ID está a ser usado
    - Se há avisos de privacidade
    """
    return await run_test_openai_api_privacy()


@router.post("/migrate-ttl-fields", response_model=TTLMigrationResponse)
async def migrate_ttl_datetime_fields(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Migra documentos existentes para incluir campos datetime nativos (*_dt).

    Os índices TTL do MongoDB requerem campos BSON Date (datetime nativo).
    Documentos antigos têm apenas campos ISO string, que NÃO funcionam com TTL.

    Este endpoint popula os campos:
    - refresh_tokens: created_at_dt
    - system_error_logs: timestamp_dt
    - emails (drafts): updated_at_dt

    Após a migração, os índices TTL começarão a purgar documentos antigos.
    """
    return await run_migrate_ttl_datetime_fields()


@router.get("/ttl-status")
async def get_ttl_index_status(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Retorna o estado dos índices TTL e contagem de documentos migrados/pendentes.
    """
    return await run_get_ttl_index_status()
