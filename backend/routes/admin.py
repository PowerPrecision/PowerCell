"""
====================================================================
ROTAS DE ADMINISTRAÇÃO — POWERCELL CRM
====================================================================

Este módulo concentra todas as operações administrativas do sistema,
organizadas nos seguintes domínios:

1. **Gestão de Utilizadores** — CRUD completo de utilizadores (criar,
   atualizar, eliminar, desativar). Inclui lógica especial para o role
   PARCEIRO (ghost user sem password) e sincronização automática de
   permissões quando o role muda.

2. **Permissões e Roles** — Leitura de permissões disponíveis,
   padrões por role, e redefinição de permissões personalizadas.

3. **Workflow de Fases** — Gestão das fases do pipeline (kanban)
   de processos: criar, editar, eliminar e corrigir duplicados.
   A eliminação de uma fase com processos associados migra esses
   processos para "Clientes em Espera".

4. **Operações de Base de Dados** — Restauro de BD a partir de backup
   S3 (DEV-only), migração de números de processo, correção de
   duplicados, e verificação de índices. Estas operações são
   intencionalmente restritas ao role ADMIN porque alteram dados
   em massa e podem causar perda irreversível de informação.

5. **Personificação (Impersonate)** — Permite ao admin/CEO ver o
   sistema como outro utilizador para troubleshooting. Inclui
   proteção contra personificação de outros admins e registo
   completo de auditoria.

6. **Dados de Treino IA** — CRUD de entradas de treino para
   personalizar o agente IA (classificação de documentos,
   mapeamentos de campos, padrões de clientes).

7. **Preferências de Notificação** — Gestão de preferências de
   notificação por utilizador (email e in-app).

8. **Registos de Clientes** — Visualização e gestão dos registos
   públicos submetidos pelo formulário.

9. **Logs e Auditoria** — Consulta de audit logs, system error logs,
   e AI import logs.

SEGURANÇA:
- A maioria dos endpoints requer role ADMIN ou CEO.
- Algumas operações destrutivas (sync-database, fix-duplicates,
  migrate-process-numbers) são DEV-only (bloqueadas em produção).
- Todas as operações sensíveis são registadas no audit log.

PORQUÊ as operações são DEV-only:
- sync-database: restaura dados de produção para dev, o que poderia
  sobrescrever dados de desenvolvimento acidentalmente em produção.
- fix-duplicates: modifica dados em massa e pode eliminar processos.
- Estas operações existem para facilitar o ciclo de desenvolvimento
  e correção de anomalias, não para uso operacional regular.
====================================================================
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from utils.input_sanitization import (
    log_sanitization_rejection
)
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


router = APIRouter(prefix="/admin", tags=["Admin"])


def _safe_float(val) -> float:
    """Converte valor para float de forma segura (helper local)."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ============== PERMISSIONS ROUTES ==============

@router.get("/permissions/available")
async def get_available_permissions(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Retorna todas as permissões disponíveis no sistema.
    Usado pelo frontend para exibir opções de permissões.
    """
    return {
        "success": True,
        "data": get_all_available_permissions()
    }


@router.get("/permissions/defaults")
async def get_default_permissions(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Retorna as permissões padrão para cada role.
    Usado pelo frontend para mostrar permissões quando muda o role.
    """
    return {
        "success": True,
        "roles": get_role_display_info(),
        "defaults": DEFAULT_PERMISSIONS_BY_ROLE
    }


@router.get("/permissions/defaults/{role}")
async def get_default_permissions_for_role_endpoint(
    role: str, 
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
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


@router.post("/users/{user_id}/reset-permissions")
async def reset_user_permissions(
    user_id: str, 
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
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


# ============== GRANULAR CAPABILITIES ROUTES ==============

class CapabilityUpdateRequest(BaseModel):
    capabilities: dict  # { "PROCESS_DELETE": true, "FINANCE_VIEW": false }


@router.get("/permissions/capabilities")
async def get_capabilities_registry(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
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


@router.get("/permissions/capabilities/by-category")
async def get_capabilities_grouped(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Retorna capabilities agrupadas por categoria (para rendering da matrix)."""
    return {
        "success": True,
        "categories": CATEGORIES,
        "capabilities_by_category": get_capabilities_by_category(),
        "role_defaults": {role: defaults for role, defaults in ROLE_CAPABILITY_DEFAULTS.items() 
                         if role not in ["cliente"]},
        "super_admin_roles": SUPER_ADMIN_ROLES,
    }


@router.put("/permissions/role-defaults/{role}")
async def update_role_defaults(
    role: str,
    request: CapabilityUpdateRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
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


@router.get("/permissions/user/{user_id}")
async def get_user_permissions(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
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


@router.put("/permissions/user/{user_id}")
async def update_user_permissions(
    user_id: str,
    request: CapabilityUpdateRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
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


# ============== WORKFLOW STATUS ROUTES ==============

@router.get("/workflow-statuses", response_model=List[WorkflowStatusResponse])
async def get_workflow_statuses(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INDEXACAO, UserRole.INTERMEDIARIO, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))):
    """Lista todas as fases do workflow ordenadas pelo campo order.

    Porquê acessível a todos os roles: as fases do workflow são
    necessárias para renderizar o kanban e os filtros de estado em
    toda a aplicação, não apenas no painel de admin.

    Args:
        user: Utilizador autenticado com qualquer role válido (injetado).

    Returns:
        List[WorkflowStatusResponse]: Lista de fases ordenadas por order.
    """
    statuses = await db.workflow_statuses.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    return [WorkflowStatusResponse(**s) for s in statuses]


@router.post("/workflow-statuses", response_model=WorkflowStatusResponse)
async def create_workflow_status(data: WorkflowStatusCreate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Cria uma nova fase no workflow do pipeline de processos.

    Verifica que não existe outra fase com o mesmo nome antes de criar.
    O campo ``internal_code`` é gerado automaticamente a partir do order
    (ex: order=3 → internal_code="03").

    Args:
        data: Dados da fase (WorkflowStatusCreate com name, label, order,
            color, description).
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        WorkflowStatusResponse: Fase criada.

    Raises:
        HTTPException(400): Se já existe uma fase com o mesmo nome.
    """
    existing = await db.workflow_statuses.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="Estado já existe")
    
    status_doc = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "label": data.label,
        "order": data.order,
        "color": data.color,
        "description": data.description,
        "is_default": False,
        "internal_code": str(data.order).zfill(2),
        "portal_label": data.portal_label,
        "visible_in_portal": data.visible_in_portal,
    }
    
    await db.workflow_statuses.insert_one(status_doc)
    return WorkflowStatusResponse(**{k: v for k, v in status_doc.items() if k != "_id"})


@router.put("/workflow-statuses/{status_id}", response_model=WorkflowStatusResponse)
async def update_workflow_status(status_id: str, data: WorkflowStatusUpdate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Atualiza os dados de uma fase do workflow existente.

    Apenas os campos fornecidos no body são atualizados (atualização
    parcial). Se nenhum campo for enviado, não efetua qualquer alteração.

    Args:
        status_id: ID da fase a atualizar.
        data: Campos a atualizar (WorkflowStatusUpdate com label, order,
            color, description — todos opcionais).
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        WorkflowStatusResponse: Fase atualizada com todos os campos.

    Raises:
        HTTPException(404): Se fase não encontrada.
    """
    status = await db.workflow_statuses.find_one({"id": status_id}, {"_id": 0})
    if not status:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    update_data = {}
    if data.label is not None:
        update_data["label"] = data.label
    if data.order is not None:
        update_data["order"] = data.order
    if data.color is not None:
        update_data["color"] = data.color
    if data.description is not None:
        update_data["description"] = data.description
    if data.portal_label is not None:
        update_data["portal_label"] = data.portal_label
    if data.visible_in_portal is not None:
        update_data["visible_in_portal"] = data.visible_in_portal
    
    if update_data:
        await db.workflow_statuses.update_one({"id": status_id}, {"$set": update_data})
    
    updated = await db.workflow_statuses.find_one({"id": status_id}, {"_id": 0})
    return WorkflowStatusResponse(**updated)


@router.delete("/workflow-statuses/{status_id}")
async def delete_workflow_status(status_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Elimina uma fase do workflow.
    
    Se houver processos associados, são movidos para "Clientes em Espera" (ou a primeira fase disponível).
    """
    status = await db.workflow_statuses.find_one({"id": status_id})
    if not status:
        raise HTTPException(status_code=404, detail="Estado não encontrado")
    
    status_name = status["name"]
    target_name = None  # Inicializar
    
    # Verificar se há processos associados
    process_count = await db.processes.count_documents({"status": status_name})
    
    if process_count > 0:
        # Encontrar a fase de destino (Clientes em Espera ou primeira fase)
        target_status = await db.workflow_statuses.find_one(
            {"name": "clientes_espera"}, 
            {"_id": 0, "name": 1, "label": 1}
        )
        
        if not target_status:
            # Se não encontrar "clientes_espera", usar a primeira fase por ordem
            target_status = await db.workflow_statuses.find_one(
                {"name": {"$ne": status_name}},
                {"_id": 0, "name": 1, "label": 1},
                sort=[("order", 1)]
            )
        
        if not target_status:
            raise HTTPException(
                status_code=400, 
                detail="Não existe outra fase para onde mover os processos"
            )
        
        target_name = target_status["name"]
        target_label = target_status.get("label", target_name)
        
        # Mover todos os processos para a fase de destino
        result = await db.processes.update_many(
            {"status": status_name},
            {"$set": {"status": target_name, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        # Registrar no histórico
        moved_count = result.modified_count
        if moved_count > 0:
            await db.history.insert_one({
                "id": str(uuid.uuid4()),
                "process_id": None,
                "user_id": user["id"],
                "user_name": user.get("name", "Admin"),
                "action": f"Fase '{status.get('label', status_name)}' eliminada - {moved_count} processos movidos para '{target_label}'",
                "field": "workflow_status_deleted",
                "old_value": status_name,
                "new_value": target_name,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
    
    # Eliminar a fase
    await db.workflow_statuses.delete_one({"id": status_id})
    
    return {
        "message": f"Fase '{status.get('label', status_name)}' eliminada",
        "processes_moved": process_count,
        "moved_to": target_name if process_count > 0 else None
    }


@router.post("/workflow-statuses/fix-duplicates")
async def fix_duplicate_workflow_statuses(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Remove fases de workflow duplicadas causadas por merge.
    Mantém apenas a primeira ocorrência de cada fase (por nome).
    """
    from collections import defaultdict
    
    # Buscar todos os workflow_statuses
    all_statuses = await db.workflow_statuses.find({}).to_list(length=None)
    
    # Agrupar por nome
    by_name = defaultdict(list)
    for status in all_statuses:
        by_name[status.get('name')].append(status)
    
    # Identificar duplicados
    duplicates_found = False
    ids_to_remove = []
    report = {"analyzed": len(all_statuses), "duplicates": [], "removed": 0}
    
    for name, statuses in by_name.items():
        if len(statuses) > 1:
            duplicates_found = True
            # Ordenar por order para manter o mais relevante
            statuses.sort(key=lambda x: x.get('order', 999))
            
            duplicate_info = {
                "name": name,
                "count": len(statuses),
                "keeping": statuses[0].get('id'),
                "removing": []
            }
            
            # Manter o primeiro, remover os restantes
            for status in statuses[1:]:
                status_id = status.get('id')
                ids_to_remove.append(status_id)
                duplicate_info["removing"].append(status_id)
            
            report["duplicates"].append(duplicate_info)
    
    if not duplicates_found:
        return {
            "success": True,
            "message": "Não foram encontrados duplicados",
            "report": report
        }
    
    # Remover duplicados
    for status_id in ids_to_remove:
        await db.workflow_statuses.delete_one({"id": status_id})
        report["removed"] += 1
    
    # Verificar resultado final
    remaining = await db.workflow_statuses.count_documents({})
    report["remaining_count"] = remaining
    
    return {
        "success": True,
        "message": f"Removidos {report['removed']} duplicados",
        "report": report
    }


@router.get("/s3/cors-status")
@router.post("/s3/fix-cors")
async def s3_cors_diagnostic(force_fix: bool = False, request: Request = None, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Diagnóstico e fix da configuração CORS do bucket S3.

    GET: Lê a config CORS atual e reporta estado.
    POST: Força a aplicação da config CORS correcta.

    O browser bloqueia uploads diretos ao S3 se não houver CORS configurado.
    """
    from services.s3_storage import s3_service, AWS_BUCKET_NAME, AWS_REGION
    from botocore.exceptions import ClientError

    result = {
        "bucket": AWS_BUCKET_NAME,
        "region": AWS_REGION,
        "service_configured": s3_service.is_configured(),
    }

    if not s3_service.is_configured():
        return {**result, "error": "S3 não configurado (faltam credenciais)"}

    # Ler CORS atual
    try:
        existing = s3_service.s3_client.get_bucket_cors(Bucket=AWS_BUCKET_NAME)
        result["current_cors"] = existing.get("CORSRules", [])
        result["has_cors"] = True
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'NoSuchCORSConfiguration':
            result["has_cors"] = False
            result["current_cors"] = None
        else:
            result["error_reading"] = str(e)
            result["has_cors"] = None

    # Aplicar CORS (só em POST ou com force_fix)
    if force_fix or (request and request.method == "POST"):
        cors_config = {
            'CORSRules': [
                {
                    'AllowedHeaders': ['Content-Type', 'x-amz-*'],
                    'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
                    'AllowedOrigins': [
                        'https://powercell.pt',
                        'https://www.powercell.pt',
                        'https://powercell-1.onrender.com',
                        'https://powercell.onrender.com',
                        'http://localhost:3000',
                        'http://localhost:5173',
                        'http://localhost:5000',
                        'http://127.0.0.1:3000',
                        'http://127.0.0.1:5173',
                    ],
                    'ExposeHeaders': [
                        'ETag',
                        'x-amz-request-id',
                        'x-amz-id-2',
                    ],
                    'MaxAgeSeconds': 3600,
                }
            ]
        }

        try:
            s3_service.s3_client.put_bucket_cors(
                Bucket=AWS_BUCKET_NAME,
                CORSConfiguration=cors_config
            )
            result["fix_applied"] = True
            result["fix_message"] = "CORS configurado com sucesso!"

            # Verificar imediatamente
            verify = s3_service.s3_client.get_bucket_cors(Bucket=AWS_BUCKET_NAME)
            result["verified_cors"] = verify.get("CORSRules", [])
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            result["fix_applied"] = False
            result["fix_error"] = f"[{error_code}] {error_msg}"
            result["fix_hint"] = (
                "A IAM key não tem permissão 's3:PutBucketCORS'. "
                "Adicione esta permissão à IAM policy OU configure CORS manualmente na AWS Console: "
                "S3 > powerprecision-docs-storage > Permissions > Cross-origin resource sharing (CORS)"
            )

    return result


@router.post("/workflow-statuses/migrate-portal-labels")
async def migrate_portal_labels(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Migração: adiciona campos portal_label e visible_in_portal aos workflow_statuses.

    Executa automaticamente ao deploy. Idempotente — pode ser chamado múltiplas vezes.
    """
    DEFAULTS = {
        "clientes_espera":    {"portal_label": "Em Espera",                   "visible_in_portal": True},
        "fase_documental":    {"portal_label": "Recolha de Documentos",        "visible_in_portal": True},
        "fase_documental_ii": {"portal_label": "Documentação Complementar",   "visible_in_portal": True},
        "enviado_bruno":      {"portal_label": "Análise do Processo",         "visible_in_portal": True},
        "enviado_luis":       {"portal_label": "Validação Interna",           "visible_in_portal": True},
        "enviado_bcp_rui":    {"portal_label": "Análise Bancária",            "visible_in_portal": True},
        "entradas_precision": {"portal_label": "Em Processamento",            "visible_in_portal": True},
        "fase_bancaria":      {"portal_label": "Aprovação Bancária",          "visible_in_portal": True},
        "fase_visitas":       {"portal_label": "Visitas ao Imóvel",           "visible_in_portal": True},
        "ch_aprovado":        {"portal_label": "Crédito Aprovado",            "visible_in_portal": True},
        "fase_escritura":     {"portal_label": "Preparação da Escritura",     "visible_in_portal": True},
        "escritura_agendada": {"portal_label": "Escritura Agendada",          "visible_in_portal": True},
        "concluidos":         {"portal_label": None,                          "visible_in_portal": False},
        "desistencias":       {"portal_label": None,                          "visible_in_portal": False},
    }

    all_statuses = await db.workflow_statuses.find({}).to_list(length=None)
    updated = 0
    skipped = 0

    for status in all_statuses:
        name = status.get("name", "")
        defaults = DEFAULTS.get(name)
        updates = {}

        if defaults:
            if "portal_label" not in status:
                updates["portal_label"] = defaults["portal_label"]
            if "visible_in_portal" not in status:
                updates["visible_in_portal"] = defaults["visible_in_portal"]
        else:
            # Status personalizado — garantir que visible_in_portal existe
            if "visible_in_portal" not in status:
                updates["visible_in_portal"] = True

        if updates:
            await db.workflow_statuses.update_one(
                {"_id": status["_id"]},
                {"$set": updates}
            )
            updated += 1
        else:
            skipped += 1

    return {
        "success": True,
        "message": f"Migration concluída: {updated} atualizados, {skipped} ignorados",
        "updated": updated,
        "skipped": skipped,
        "total": len(all_statuses),
    }


@router.post("/processes/fix-duplicates")
async def fix_duplicate_processes(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """
    Remove processos duplicados causados por merge.
    
    Identifica duplicados por:
    1. Mesmo email (client_email)
    2. Mesmo NIF (personal_data.nif)
    
    Mantém o processo mais recente (maior created_at) e remove os mais antigos.
    """
    from collections import defaultdict
    
    # Buscar todos os processos
    all_processes = await db.processes.find({}).to_list(length=None)
    
    # Agrupar por email
    by_email = defaultdict(list)
    # Agrupar por NIF
    by_nif = defaultdict(list)
    
    for proc in all_processes:
        email = proc.get("client_email", "").lower().strip() if proc.get("client_email") else None
        nif = proc.get("personal_data", {}).get("nif") if proc.get("personal_data") else None
        
        if email:
            by_email[email].append(proc)
        if nif:
            by_nif[nif].append(proc)
    
    # Identificar duplicados
    ids_to_remove = set()
    report = {
        "analyzed": len(all_processes),
        "duplicates_by_email": [],
        "duplicates_by_nif": [],
        "removed": 0
    }
    
    # Processar duplicados por email
    for email, procs in by_email.items():
        if len(procs) > 1:
            # Ordenar por created_at descendente (mais recente primeiro)
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            duplicate_info = {
                "key": email,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente, remover os outros
            for proc in procs[1:]:
                proc_id = proc.get("id")
                if proc_id not in ids_to_remove:
                    ids_to_remove.add(proc_id)
                    duplicate_info["removing"].append({
                        "id": proc_id,
                        "name": proc.get("client_name"),
                        "created_at": proc.get("created_at")
                    })
            
            report["duplicates_by_email"].append(duplicate_info)
    
    # Processar duplicados por NIF
    for nif, procs in by_nif.items():
        if len(procs) > 1:
            # Ordenar por created_at descendente
            procs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            duplicate_info = {
                "key": nif,
                "count": len(procs),
                "keeping": procs[0].get("id"),
                "keeping_name": procs[0].get("client_name"),
                "removing": []
            }
            
            # Manter o mais recente, remover os outros (se ainda não marcados)
            for proc in procs[1:]:
                proc_id = proc.get("id")
                if proc_id not in ids_to_remove:
                    ids_to_remove.add(proc_id)
                    duplicate_info["removing"].append({
                        "id": proc_id,
                        "name": proc.get("client_name"),
                        "created_at": proc.get("created_at")
                    })
            
            report["duplicates_by_nif"].append(duplicate_info)
    
    total_duplicates = len(report["duplicates_by_email"]) + len(report["duplicates_by_nif"])
    
    if total_duplicates == 0:
        return {
            "success": True,
            "message": "Não foram encontrados processos duplicados",
            "report": report
        }
    
    # Remover duplicados
    for proc_id in ids_to_remove:
        # Mover documentos associados para o processo mantido? Não, apagar tudo
        await db.documents.delete_many({"process_id": proc_id})
        await db.tasks.delete_many({"process_id": proc_id})
        await db.history.delete_many({"process_id": proc_id})
        await db.processes.delete_one({"id": proc_id})
        report["removed"] += 1
    
    # Registrar no histórico
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": None,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": f"Correção de processos duplicados - {report['removed']} processos removidos",
        "field": "process_duplicates_fixed",
        "old_value": None,
        "new_value": str(report["removed"]),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Verificar resultado final
    remaining = await db.processes.count_documents({})
    report["remaining_count"] = remaining
    
    return {
        "success": True,
        "message": f"Removidos {report['removed']} processos duplicados",
        "report": report
    }


# ============== USER MANAGEMENT ROUTES ==============

@router.get("/users", response_model=List[UserResponse])
async def get_users(role: Optional[str] = None, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO]))):
    """Lista utilizadores do sistema, opcionalmente filtrados por role.

    O campo password é excluído da resposta por segurança.
    Acessível a Admin, CEO, Diretor, Consultor e Intermediário porque
    estes roles precisam de ver informações de utilizadores para
    atribuição de processos e colaboração.

    Args:
        role: Filtro opcional por role (ex: "consultor", "admin").
        user: Utilizador autenticado com role permitido (injetado).

    Returns:
        List[UserResponse]: Lista de utilizadores (sem password).
    """
    from services.role_query import build_deep_role_query
    query = {}
    if role:
        query = build_deep_role_query(query, role=role)
    
    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(1000)
    return [UserResponse(**u) for u in users]


@router.post("/users", response_model=UserResponse)
async def create_user(data: UserCreate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Cria um novo utilizador no sistema com lógica diferenciada por role.

    Este endpoint suporta dois fluxos distintos de criação:

    **Utilizadores normais** (Consultor, Intermediário, Diretor, etc.):
    - Valida presença de email, password e role válido.
    - Verifica unicidade do email.
    - Envia email de boas-vindas com credenciais (não falha a criação
      se o email não for enviado).
    - Associa automaticamente processos do Trello cujo nome do membro
      corresponda ao nome do utilizador criado.

    **Parceiros** (ghost users):
    - Apenas requer nome. Email/password não são necessários porque
      parceiros não acedem ao sistema diretamente — servem apenas para
      associação a processos como entidades externas.
    - Gera um email placeholder único para satisfazer a constraint de
      unicidade sem reservar emails reais.

    Porquê o CLIENTE não pode ser criado aqui: no PowerCell, clientes
    são representados por processos (não por utilizadores do sistema).
    Um cliente submete o formulário público e é criado como processo.

    Args:
        data: Dados do utilizador (UserCreate com email, name, phone,
            password, role, onedrive_folder).
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        UserResponse: Dados do utilizador criado (sem password).

    Raises:
        HTTPException(400): Se role é CLIENTE, role inválido, email já
            registado, password em falta, ou nome em falta (parceiro).
    """
    # Sanitizar inputs (sem validação restritiva — aceitar qualquer valor)
    clean_email = (data.email or "").strip().lower()
    clean_name = (data.name or "").strip()
    clean_phone = (data.phone or "").strip() if data.phone else None
    
    # Cliente não é um utilizador do sistema - é um processo
    if data.role == UserRole.CLIENTE:
        raise HTTPException(status_code=400, detail="Cliente não pode ser criado como utilizador. O cliente é representado pelo processo.")
    
    # Validar role - inclui PARCEIRO
    valid_roles = [UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO, UserRole.CEO, UserRole.ADMIN, UserRole.PARCEIRO]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail="Role inválido")
    
    # PARCEIRO é um "ghost user" - apenas precisa do nome
    is_parceiro = data.role == UserRole.PARCEIRO
    
    if is_parceiro:
        # Para parceiros: nome é obrigatório, email/password não são necessários
        if not clean_name:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        
        # Gerar email placeholder único para parceiros (para não violar unique constraint)
        import uuid as uuid_module
        placeholder_email = f"parceiro_{uuid_module.uuid4().hex[:8]}@placeholder.internal"
        
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        user_doc = {
            "id": user_id,
            "email": placeholder_email,
            "password": None,  # Sem password para parceiros
            "name": clean_name,
            "phone": clean_phone,
            "role": data.role,
            "additional_roles": data.additional_roles or [],
            "is_active": True,
            "onedrive_folder": None,  # Parceiros não precisam de pasta
            "base_salary": _safe_float(data.base_salary),  # Vencimento fixo mensal
            "created_at": now
        }
        
        await db.users.insert_one(user_doc)
        await _audit_log("user_created", "user", user_id, user, {"role": data.role, "additional_roles": data.additional_roles, "name": clean_name, "type": "parceiro_ghost"})
        
        # Não enviar email de boas-vindas para parceiros
        return UserResponse(**user_doc)
    
    # Para outros roles: validar email e password
    existing = await db.users.find_one({"email": clean_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    # Validar password (apenas presença — sem validação de força)
    if not data.password:
        raise HTTPException(status_code=400, detail="Password é obrigatória")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": clean_email,
        "password": hash_password(data.password),
        "name": clean_name,
        "phone": clean_phone,
        "role": data.role,
        "additional_roles": data.additional_roles or [],
        "is_active": True,
        "onedrive_folder": data.onedrive_folder or clean_name,
        "base_salary": _safe_float(data.base_salary),  # Vencimento fixo mensal
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    await _audit_log("user_created", "user", user_id, user, {"email": clean_email, "role": data.role, "additional_roles": data.additional_roles, "name": clean_name})
    
    # Enviar email de boas-vindas com dados de acesso
    try:
        from services.email_service import send_email
        
        # Determinar o nome do cargo em português
        role_names = {
            UserRole.CONSULTOR: "Consultor",
            UserRole.INTERMEDIARIO: "Intermediário",
            UserRole.DIRETOR: "Diretor",
            UserRole.ADMINISTRATIVO: "Administrativo",
            UserRole.INDEXACAO: "Indexação",
            UserRole.CEO: "CEO",
            UserRole.ADMIN: "Administrador"
        }
        role_name = role_names.get(data.role, data.role)
        
        # Criar corpo do email
        email_body = f"""Olá {clean_name},

Bem-vindo(a) ao PowerCell!

A sua conta foi criada com sucesso. Seguem os dados de acesso:

📧 Email: {clean_email}
🔑 Password: {data.password}

Perfil: {role_name}

🔗 Aceda à plataforma em: https://powercell.vercel.app

Recomendamos que altere a sua password após o primeiro acesso.

Se tiver alguma dúvida, não hesite em contactar.

Cumprimentos,
Equipa PowerCell
"""
        
        email_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Bem-vindo ao PowerCell</h1>
            </div>
            <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; border: 1px solid #e2e8f0; border-top: none;">
                <p style="font-size: 16px; color: #334155;">Olá <strong>{data.name}</strong>,</p>
                <p style="font-size: 16px; color: #334155;">A sua conta foi criada com sucesso. Seguem os dados de acesso:</p>
                
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0;">
                    <p style="margin: 10px 0;"><strong>📧 Email:</strong> {data.email}</p>
                    <p style="margin: 10px 0;"><strong>🔑 Password:</strong> <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{data.password}</code></p>
                    <p style="margin: 10px 0;"><strong>👤 Perfil:</strong> {role_name}</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://powercell.vercel.app" style="background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); color: white; padding: 12px 30px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">
                        Aceder à Plataforma
                    </a>
                </div>
                
                <p style="font-size: 14px; color: #64748b; background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;">
                    ⚠️ Recomendamos que altere a sua password após o primeiro acesso.
                </p>
                
                <p style="font-size: 14px; color: #64748b; margin-top: 30px;">
                    Se tiver alguma dúvida, não hesite em contactar.<br><br>
                    Cumprimentos,<br>
                    <strong>Equipa PowerCell</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        # Enviar email (usar conta power ou precision)
        email_result = await send_email(
            account_name="power",  # Usar conta Power Real Estate
            to_emails=[clean_email],
            subject="Bem-vindo ao PowerCell - Dados de Acesso",
            body=email_body,
            body_html=email_html
        )
        
        if email_result.get("success"):
            logger.info(f"Email de boas-vindas enviado para {data.email}")
        else:
            logger.warning(f"Não foi possível enviar email para {data.email}: {email_result.get('error')}")
            
    except Exception as e:
        logger.warning(f"Erro ao enviar email de boas-vindas: {e}")
        # Não falhar a criação do utilizador se o email falhar
    
    # Associar automaticamente processos do Trello que têm este utilizador atribuído
    # Verifica se o nome do utilizador corresponde a algum membro atribuído no Trello
    name_lower = clean_name.lower()
    name_parts = [p for p in name_lower.split() if len(p) >= 3]
    
    # Procurar processos com trello_members que corresponda ao nome
    query = {"trello_members": {"$exists": True, "$ne": []}}
    processes_to_update = await db.processes.find(query, {"_id": 0, "id": 1, "trello_members": 1}).to_list(1000)
    
    updated_count = 0
    for proc in processes_to_update:
        members = proc.get("trello_members", [])
        # Verificar se o nome do utilizador está na lista de membros
        for member in members:
            member_lower = member.lower()
            # Verificar se alguma parte do nome corresponde
            if any(part in member_lower for part in name_parts):
                # Determinar qual campo actualizar baseado no role
                if data.role in [UserRole.CONSULTOR]:
                    await db.processes.update_one(
                        {"id": proc["id"]},
                        {"$set": {"assigned_consultor_id": user_id}}
                    )
                    updated_count += 1
                elif data.role == UserRole.INTERMEDIARIO:
                    await db.processes.update_one(
                        {"id": proc["id"]},
                        {"$set": {"assigned_mediador_id": user_id}}
                    )
                    updated_count += 1
                break  # Já encontrou match, passar ao próximo processo
    
    if updated_count > 0:
        logger.info(f"Utilizador {data.name} criado e associado a {updated_count} processos automaticamente")
    
    return UserResponse(
        id=user_id,
        email=clean_email,
        name=clean_name,
        phone=clean_phone,
        role=data.role,
        created_at=now,
        onedrive_folder=data.onedrive_folder or clean_name
    )


async def _audit_log(action: str, entity: str, entity_id: str, performed_by: dict, details: dict = None):
    """Regista uma ação crítica no audit log para rastreabilidade.

    O audit log é usado para manter um histórico permanente de
    operações sensíveis (criação/eliminação de utilizadores,
    restauros de BD, reset de permissões, etc.).

    Este método é tolerante a falhas: se a escrita no audit log
    falhar (ex: problema de conexão à BD), o erro é registado no
    logger mas NÃO é propagado — evitando que uma falha de auditoria
    bloqueie a operação principal.

    Args:
        action: Identificador da ação (ex: "user_created", "user_deleted",
            "restore_dev_from_backup", "permissions_reset").
        entity: Tipo de entidade afetada (ex: "user", "database").
        entity_id: ID da entidade afetada.
        performed_by: Dicionário do utilizador que executou a ação
            (deve conter "id", "name", "email").
        details: Dicionário opcional com metadados adicionais sobre
            a ação executada.
    """
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "performed_by_id": performed_by.get("id"),
            "performed_by_name": performed_by.get("name"),
            "performed_by_email": performed_by.get("email"),
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning(f"Audit log falhou: {e}")


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, data: UserUpdate, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Atualiza os dados de um utilizador existente.

    Este endpoint suporta a atualização de todos os campos editáveis
    do utilizador, com regras de negócio específicas:

    - **Email**: Verifica unicidade contra outros utilizadores.
    - **Role**: Se alterado, sincroniza automaticamente as permissões
      com o novo role (a menos que o utilizador tenha permissões
      personalizadas — nesse caso mantém as personalizadas).
    - **is_active**: Protege o utilizador administrador de ser
      desativado (um admin desativado não poderia ser reativado).
    - **Password**: Hasha a nova password antes de guardar.
    - **Permissões explícitas**: Se o admin fornecer permissões no
      body, essas sobrepõem-se às padrão do role.

    Porquê a sincronização automática de permissões: quando o role
    de um utilizador muda (ex: Consultor → Diretor), as suas
    permissões devem refletir as capacidades do novo cargo. No
    entanto, se o admin definiu permissões personalizadas manualmente,
    essas são preservadas para não destruir configurações deliberadas.

    Args:
        user_id: ID do utilizador a atualizar.
        data: Campos a atualizar (UserUpdate com name, phone, email,
            role, is_active, password, permissions, onedrive_folder).
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        UserResponse: Dados atualizados do utilizador (sem password).

    Raises:
        HTTPException(404): Se utilizador não encontrado.
        HTTPException(400): Se email já existe noutro utilizador,
            role inválido, ou tentativa de desativar um admin.
    """
    from services.permissions import (
        get_default_permissions_for_role, 
        should_sync_permissions,
        validate_permissions
    )
    
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    update_data = {}
    role_changed = False
    old_role = target_user.get("role")
    
    if data.name is not None:
        update_data["name"] = (data.name or "").strip()
    if data.phone is not None:
        update_data["phone"] = (data.phone or "").strip() if data.phone else None
    if data.email is not None:
        clean_email = (data.email or "").strip().lower()
        if clean_email:
            # Verificar se email já existe noutro utilizador
            existing = await db.users.find_one({"email": clean_email, "id": {"$ne": user_id}})
            if existing:
                raise HTTPException(status_code=400, detail="Email já registado noutro utilizador")
            update_data["email"] = clean_email
    if data.role is not None:
        if data.role not in [UserRole.CLIENTE, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO, UserRole.CEO, UserRole.ADMIN]:
            raise HTTPException(status_code=400, detail="Role inválido")
        if data.role != old_role:
            role_changed = True
        update_data["role"] = data.role
    if data.is_active is not None:
        # Proteger admin de ser desactivado
        if target_user.get("role") == "admin" and data.is_active == False:
            raise HTTPException(status_code=400, detail="Não é possível desactivar o utilizador administrador")
        update_data["is_active"] = data.is_active
    if data.onedrive_folder is not None:
        update_data["onedrive_folder"] = data.onedrive_folder
    # Processar base_salary (vencimento fixo mensal — modelo híbrido)
    if data.base_salary is not None:
        salary = _safe_float(data.base_salary)
        if salary < 0:
            raise HTTPException(status_code=400, detail="Salário fixo não pode ser negativo")
        update_data["base_salary"] = salary
    # Processar additional_roles (múltiplos perfis)
    if data.additional_roles is not None:
        update_data["additional_roles"] = data.additional_roles
    # Processar alteração de password (apenas admin pode alterar password de outros)
    if data.password is not None and data.password.strip():
        update_data["password"] = hash_password(data.password)
    
    # Processar permissões - sincronizar automaticamente quando o role muda
    current_permissions = target_user.get("permissions")
    new_role = data.role or old_role
    
    if data.permissions is not None:
        # Se o admin está a definir permissões explicitamente, usar essas
        update_data["permissions"] = validate_permissions(data.permissions)
    elif role_changed:
        # Se o role mudou, sincronizar permissões com o novo role
        # Apenas sincronizar se o utilizador não tinha permissões personalizadas
        if should_sync_permissions(old_role, new_role, current_permissions):
            update_data["permissions"] = get_default_permissions_for_role(new_role)
            logger.info(f"Permissões sincronizadas para utilizador {user_id}: {old_role} -> {new_role}")
        # Se tinha permissões personalizadas, manter (admin pode redefinir manualmente)
    
    if update_data:
        await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return UserResponse(**updated)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """Elimina permanentemente um utilizador do sistema.

    Este endpoint remove o utilizador da base de dados de forma
    irreversível. Por segurança, impede que um utilizador elimine
    a sua própria conta (o que causaria sessão órfã).

    Nota: a eliminação não remove processos, documentos, ou histórico
    associados ao utilizador. Esses dados permanecem no sistema para
    preservar a integridade do histórico de processos.

    Args:
        user_id: ID do utilizador a eliminar.
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: Mensagem de confirmação ``{"message": "Utilizador eliminado"}``.

    Raises:
        HTTPException(400): Se tentar eliminar a própria conta.
        HTTPException(404): Se utilizador não encontrado.
    """
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Não pode eliminar a própria conta")
    
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1, "role": 1})
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    await _audit_log("user_deleted", "user", user_id, user, {"deleted_email": target.get("email"), "deleted_name": target.get("name"), "deleted_role": target.get("role")})
    return {"message": "Utilizador eliminado"}


# ============== IMPERSONATE (VER COMO OUTRO UTILIZADOR) ==============

@router.post("/impersonate/{user_id}")
async def impersonate_user(user_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Permite ao admin/CEO ver o sistema como outro utilizador, gerando
    um token temporário com os dados e permissões do utilizador alvo.

    Porquê este endpoint existe: essencial para suporte técnico e
    troubleshooting — permite ao admin reproduzir exatamente o que o
    utilizador vê (permissões, dados visíveis, interface) sem precisar
    de partilhar passwords ou usar a conta de outro utilizador.

    Garantias de segurança:
    - Impedir personificação de outros admins (autoproteção).
    - Token inclui campos de auditoria (impersonated_by, is_impersonated).
    - Toda a ação realizada durante impersonate é registada no histórico.

    Args:
        user_id: ID do utilizador a personificar.
        user: Utilizador admin/CEO autenticado (injetado pelo Depends).

    Returns:
        dict: Novo access_token e dados do utilizador personificado,
            incluindo campos de auditoria (impersonated_by, is_impersonated).

    Raises:
        HTTPException: 404 se utilizador não encontrado, 403 se tentar
            personificar outro administrador.
    """
    from services.auth import create_access_token
    
    # Verificar que o utilizador alvo existe
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Não permitir impersonate de outro admin
    if target_user["role"] == UserRole.ADMIN and user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Não pode personificar outro administrador")
    
    # Criar token com dados do utilizador alvo, mas marcar como impersonated
    token_data = {
        "sub": target_user["id"],
        "email": target_user["email"],
        "role": target_user["role"],
        "name": target_user["name"],
        # Informação de auditoria
        "impersonated_by": user["id"],
        "impersonated_by_name": user["name"],
        "is_impersonated": True
    }
    
    access_token = create_access_token(token_data)
    
    # Log da acção
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": None,
        "user_id": user["id"],
        "user_name": user["name"],
        "action": f"Admin impersonou utilizador: {target_user['name']} ({target_user['email']})",
        "field": "impersonate",
        "old_value": None,
        "new_value": target_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": target_user["id"],
            "email": target_user["email"],
            "name": target_user["name"],
            "role": target_user["role"],
            "is_impersonated": True,
            "impersonated_by": user["id"],
            "impersonated_by_name": user["name"]
        }
    }


@router.post("/stop-impersonate")
async def stop_impersonate(user: dict = Depends(get_current_user)):
    """
    Termina a sessão de personificação e restaura a conta original do admin.

    Porquê um endpoint dedicado: o token do utilizador personificado não
    contém a password do admin original, pelo que não é possível fazer
    login diretamente. Este endpoint usa o campo ``impersonated_by`` do
    token atual para identificar o admin original e gerar um novo token.

    Args:
        user: Utilizador atualmente em modo de personificação (o token
            contém o campo impersonated_by com o ID do admin original).

    Returns:
        dict: Novo access_token para a conta original do admin e dados
            do administrador (sem campos de personificação).

    Raises:
        HTTPException: 400 se não está em modo de personificação,
            404 se o admin original não foi encontrado.
    """
    from services.auth import create_access_token
    
    if not user.get("impersonated_by"):
        raise HTTPException(status_code=400, detail="Não está em modo de personificação")
    
    # Buscar o admin original
    admin_user = await db.users.find_one({"id": user["impersonated_by"]}, {"_id": 0, "password": 0})
    if not admin_user:
        raise HTTPException(status_code=404, detail="Administrador original não encontrado")
    
    # Criar novo token para o admin
    token_data = {
        "sub": admin_user["id"],
        "email": admin_user["email"],
        "role": admin_user["role"],
        "name": admin_user["name"]
    }
    
    access_token = create_access_token(token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": admin_user["id"],
            "email": admin_user["email"],
            "name": admin_user["name"],
            "role": admin_user["role"]
        }
    }


# ============== PROCESS NUMBER MIGRATION ==============

@router.post("/migrate-process-numbers")
async def migrate_process_numbers(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Atribui números sequenciais a processos que ainda não têm.

    Os processos sem ``process_number`` são ordenados por data de
    criação (mais antigos primeiro) e recebem números a partir do
    último número existente + 1.

    Porquê uma migração dedicada: durante a migração de dados do
    Trello, muitos processos foram criados sem número sequencial.
    Este endpoint resolve essa lacuna de forma controlada e idempotente
    (pode ser executado múltiplas vezes sem duplicar números).

    Args:
        user: Utilizador admin autenticado (injetado).

    Returns:
        dict: Relatório com message, updated, first_number, last_number.
    """
    # Buscar processos sem número, ordenados por data de criação
    processes_without_number = await db.processes.find(
        {"$or": [{"process_number": {"$exists": False}}, {"process_number": None}]},
        {"_id": 0, "id": 1, "created_at": 1, "client_name": 1}
    ).sort("created_at", 1).to_list(10000)
    
    if not processes_without_number:
        return {"message": "Todos os processos já têm número atribuído", "updated": 0}
    
    # Obter o maior número existente
    max_result = await db.processes.find_one(
        {"process_number": {"$exists": True, "$ne": None}},
        {"process_number": 1},
        sort=[("process_number", -1)]
    )
    
    next_number = (max_result["process_number"] + 1) if max_result and max_result.get("process_number") else 1
    
    updated_count = 0
    for process in processes_without_number:
        await db.processes.update_one(
            {"id": process["id"]},
            {"$set": {"process_number": next_number}}
        )
        next_number += 1
        updated_count += 1
    
    return {
        "message": f"Números atribuídos a {updated_count} processos",
        "updated": updated_count,
        "first_number": next_number - updated_count,
        "last_number": next_number - 1
    }


@router.post("/update-process-active-status")
async def update_process_active_status(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Recalcula o campo ``is_active`` de todos os processos baseado no status.

    Processos com status "desistencias" ou "concluidos" são marcados como
    ``is_active=False``. Todos os restantes são marcados como ``is_active=True``.

    Porquê este endpoint existe: durante a migração do Trello e desenvolvimento
    iterativo, o campo ``is_active`` pode ficar dessincronizado do status.
    Este endpoint corrige essa inconsistência em massa.

    Args:
        user: Utilizador admin autenticado (injetado).

    Returns:
        dict: Relatório com inactive_updated, active_updated, total_updated.
    """
    # Status que devem ser marcados como inativos
    inactive_statuses = ["desistencias", "concluidos"]
    
    # Actualizar processos inativos
    inactive_result = await db.processes.update_many(
        {"status": {"$in": inactive_statuses}},
        {"$set": {"is_active": False}}
    )
    
    # Actualizar processos ativos (todos os outros)
    active_result = await db.processes.update_many(
        {"status": {"$nin": inactive_statuses}},
        {"$set": {"is_active": True}}
    )
    
    return {
        "message": "Status de atividade atualizado",
        "inactive_updated": inactive_result.modified_count,
        "active_updated": active_result.modified_count,
        "total_updated": inactive_result.modified_count + active_result.modified_count
    }


# ============== NOTIFICATION PREFERENCES ==============

# Default notification preferences
DEFAULT_NOTIFICATION_PREFS = {
    "email_new_process": False,  # Novo processo criado
    "email_status_change": False,  # Mudança de status de processo
    "email_document_upload": False,  # Documento carregado
    "email_task_assigned": False,  # Tarefa atribuída
    "email_deadline_reminder": True,  # Lembrete de prazo (importante)
    "email_urgent_only": True,  # Apenas urgentes
    "email_daily_summary": True,  # Resumo diário
    "email_weekly_report": True,  # Relatório semanal
    "inapp_new_process": True,
    "inapp_status_change": True,
    "inapp_document_upload": True,
    "inapp_task_assigned": True,
    "inapp_comments": True,
    "is_test_user": False,  # Se true, não recebe emails
}


# ============== AI TRAINING DATA (Item 4 - Outros erros/melhorias) ==============

@router.get("/ai-training")
async def get_ai_training_data(
    category: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém os dados de treino personalizados do agente IA.
    
    Categorias:
    - document_types: Tipos de documentos e como classificá-los
    - field_mappings: Mapeamento de campos para extração
    - client_patterns: Padrões de nomes de clientes
    - custom_rules: Regras personalizadas
    """
    query = {"type": "ai_training"}
    if category:
        query["category"] = category
    
    entries = await db.ai_training.find(query, {"_id": 0}).to_list(100)
    
    # Agrupar por categoria
    by_category = {}
    for entry in entries:
        cat = entry.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)
    
    return {
        "total": len(entries),
        "categories": list(by_category.keys()),
        "data": by_category
    }


@router.post("/ai-training")
async def add_ai_training_entry(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Adiciona uma nova entrada de treino para o agente IA.
    
    Body:
    {
        "category": "document_types",  // ou field_mappings, client_patterns, custom_rules
        "title": "Título descritivo",
        "content": "Conteúdo de treino / instruções para a IA",
        "examples": ["exemplo1", "exemplo2"],  // Opcional
        "is_active": true  // Se deve ser usado pelo agente
    }
    """
    required_fields = ["category", "title", "content"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo '{field}' é obrigatório")
    
    valid_categories = ["document_types", "field_mappings", "client_patterns", "custom_rules", "extraction_tips"]
    if data["category"] not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {valid_categories}")
    
    entry = {
        "id": str(uuid.uuid4()),
        "type": "ai_training",
        "category": data["category"],
        "title": data["title"],
        "content": data["content"],
        "examples": data.get("examples", []),
        "is_active": data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user.get("email", "admin"),
        "updated_at": None
    }
    
    await db.ai_training.insert_one(entry)
    
    return {
        "success": True,
        "entry": {k: v for k, v in entry.items() if k != "_id"}
    }


@router.put("/ai-training/{entry_id}")
async def update_ai_training_entry(
    entry_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualiza uma entrada de treino existente.
    """
    existing = await db.ai_training.find_one({"id": entry_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    
    update_data = {}
    if "title" in data:
        update_data["title"] = data["title"]
    if "content" in data:
        update_data["content"] = data["content"]
    if "examples" in data:
        update_data["examples"] = data["examples"]
    if "is_active" in data:
        update_data["is_active"] = data["is_active"]
    if "category" in data:
        valid_categories = ["document_types", "field_mappings", "client_patterns", "custom_rules", "extraction_tips"]
        if data["category"] not in valid_categories:
            raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {valid_categories}")
        update_data["category"] = data["category"]
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("email", "admin")
    
    await db.ai_training.update_one(
        {"id": entry_id},
        {"$set": update_data}
    )
    
    updated = await db.ai_training.find_one({"id": entry_id}, {"_id": 0})
    return {"success": True, "entry": updated}


@router.delete("/ai-training/{entry_id}")
async def delete_ai_training_entry(
    entry_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Remove uma entrada de treino.
    """
    result = await db.ai_training.delete_one({"id": entry_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    
    return {"success": True, "message": "Entrada removida"}


@router.get("/ai-training/prompt")
async def get_ai_training_prompt(
    category: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Gera o prompt de treino consolidado a partir das entradas activas.
    Este prompt é usado pelo agente IA durante a análise de documentos.
    """
    query = {"type": "ai_training", "is_active": True}
    if category:
        query["category"] = category
    
    entries = await db.ai_training.find(query, {"_id": 0}).sort("category", 1).to_list(100)
    
    # Construir prompt por categoria
    prompt_sections = []
    
    # Agrupar por categoria
    by_category = {}
    for entry in entries:
        cat = entry.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)
    
    category_titles = {
        "document_types": "## Tipos de Documentos",
        "field_mappings": "## Mapeamento de Campos",
        "client_patterns": "## Padrões de Nomes de Clientes",
        "custom_rules": "## Regras Personalizadas",
        "extraction_tips": "## Dicas de Extracção"
    }
    
    for cat, cat_entries in by_category.items():
        section = category_titles.get(cat, f"## {cat.title()}")
        section += "\n"
        
        for entry in cat_entries:
            section += f"\n### {entry['title']}\n"
            section += entry["content"] + "\n"
            
            if entry.get("examples"):
                section += "\nExemplos:\n"
                for ex in entry["examples"]:
                    section += f"- {ex}\n"
        
        prompt_sections.append(section)
    
    full_prompt = "\n\n".join(prompt_sections)
    
    return {
        "prompt": full_prompt,
        "entries_count": len(entries),
        "categories": list(by_category.keys())
    }


@router.post("/ai-training/prompt/execute")
async def record_ai_prompt_execution(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    O23 - Regista uma execução do prompt de treino de IA.
    Incrementa o contador de execuções.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Incrementar contador global de execuções
    await db.ai_config.update_one(
        {"type": "execution_stats"},
        {
            "$inc": {"total_executions": 1},
            "$set": {"last_executed_at": now, "last_executed_by": user.get("name", "unknown")},
            "$setOnInsert": {"type": "execution_stats", "created_at": now}
        },
        upsert=True
    )
    
    # Retornar stats actualizadas
    stats = await db.ai_config.find_one({"type": "execution_stats"}, {"_id": 0})
    return {
        "success": True,
        "total_executions": stats.get("total_executions", 1),
        "last_executed_at": stats.get("last_executed_at"),
        "last_executed_by": stats.get("last_executed_by")
    }


@router.get("/ai-training/stats")
async def get_ai_training_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """O23 - Obtém estatísticas de uso do AI Training."""
    stats = await db.ai_config.find_one({"type": "execution_stats"}, {"_id": 0}) or {}
    entries_count = await db.ai_training.count_documents({"type": "ai_training", "is_active": True})
    
    return {
        "total_executions": stats.get("total_executions", 0),
        "last_executed_at": stats.get("last_executed_at"),
        "last_executed_by": stats.get("last_executed_by"),
        "active_entries": entries_count
    }


@router.get("/notification-preferences/{user_id}")
async def get_notification_preferences(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém as preferências de notificação de um utilizador.
    Admin pode ver/editar de qualquer utilizador.
    """
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Obter preferências da DB ou usar defaults
    prefs = await db.notification_preferences.find_one({"user_id": user_id}, {"_id": 0})
    
    if not prefs:
        prefs = {**DEFAULT_NOTIFICATION_PREFS, "user_id": user_id}
    
    return {
        "user_id": user_id,
        "user_email": target_user.get("email"),
        "user_name": target_user.get("name"),
        "preferences": prefs
    }


@router.put("/notification-preferences/{user_id}")
async def update_notification_preferences(
    user_id: str,
    preferences: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualiza as preferências de notificação de um utilizador.
    Admin pode editar de qualquer utilizador.
    """
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Filtrar apenas campos válidos
    valid_keys = set(DEFAULT_NOTIFICATION_PREFS.keys())
    filtered_prefs = {k: v for k, v in preferences.items() if k in valid_keys}
    
    filtered_prefs["user_id"] = user_id
    filtered_prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    filtered_prefs["updated_by"] = user.get("email", "admin")
    
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": filtered_prefs},
        upsert=True
    )
    
    # Invalidar cache de preferências de notificação
    try:
        from services.realtime_notifications import _invalidate_pref_cache
        _invalidate_pref_cache(user_id)
    except ImportError:
        pass
    
    return {"success": True, "preferences": filtered_prefs}


@router.get("/notification-preferences")
async def get_all_notification_preferences(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Lista preferências de todos os utilizadores."""
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}).to_list(500)
    
    result = []
    for u in users:
        prefs = await db.notification_preferences.find_one({"user_id": u["id"]}, {"_id": 0})
        if not prefs:
            prefs = {**DEFAULT_NOTIFICATION_PREFS, "user_id": u["id"]}
        
        result.append({
            "user_id": u["id"],
            "email": u.get("email"),
            "name": u.get("name"),
            "role": u.get("role"),
            "receives_email": not prefs.get("is_test_user", False) and (
                prefs.get("email_urgent_only") or 
                prefs.get("email_daily_summary") or
                prefs.get("email_weekly_report")
            ),
            "is_test_user": prefs.get("is_test_user", False)
        })
    
    return result


@router.post("/notification-preferences/bulk-update")
async def bulk_update_notification_preferences(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Actualiza preferências de múltiplos utilizadores de uma vez.
    
    Body:
    {
        "user_ids": ["id1", "id2"],
        "preferences": {"is_test_user": true}
    }
    """
    user_ids = data.get("user_ids", [])
    preferences = data.get("preferences", {})
    
    if not user_ids:
        raise HTTPException(status_code=400, detail="user_ids é obrigatório")
    
    valid_keys = set(DEFAULT_NOTIFICATION_PREFS.keys())
    filtered_prefs = {k: v for k, v in preferences.items() if k in valid_keys}
    filtered_prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    filtered_prefs["updated_by"] = user.get("email", "admin")
    
    updated = 0
    for uid in user_ids:
        result = await db.notification_preferences.update_one(
            {"user_id": uid},
            {"$set": {**filtered_prefs, "user_id": uid}},
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            updated += 1
    
    # Invalidar cache de preferências de notificação para todos os utilizadores afectados
    try:
        from services.realtime_notifications import _invalidate_pref_cache
        for uid in user_ids:
            _invalidate_pref_cache(uid)
    except ImportError:
        pass
    
    return {"success": True, "updated_count": updated}


# ============== SYSTEM ERROR LOGS ==============

@router.get("/system-logs")
async def get_system_error_logs(
    page: int = 1,
    limit: int = 50,
    severity: str = None,
    component: str = None,
    error_type: str = None,
    resolved: bool = None,
    days: int = 7,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de erros do sistema com filtros e paginação.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - severity: Filtrar por severidade (info, warning, error, critical)
    - component: Filtrar por componente (scraper, auth, processes, etc.)
    - error_type: Filtrar por tipo de erro
    - resolved: True/False para filtrar resolvidos/não resolvidos
    - days: Últimos N dias (default 7)
    """
    from services.system_error_logger import system_error_logger
    return await system_error_logger.get_errors(
        page=page,
        limit=limit,
        severity=severity,
        component=component,
        error_type=error_type,
        resolved=resolved,
        days=days
    )


@router.get("/system-logs/stats")
async def get_system_logs_stats(
    days: int = 7,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém estatísticas de erros dos últimos N dias."""
    from services.system_error_logger import system_error_logger
    return await system_error_logger.get_stats(days)


@router.get("/system-logs/{error_id}")
async def get_system_log_detail(
    error_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém detalhes de um erro específico."""
    from services.system_error_logger import system_error_logger
    error = await system_error_logger.get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    return error


@router.post("/system-logs/mark-read")
async def mark_errors_as_read(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca erros como lidos.
    
    Body: {"error_ids": ["id1", "id2"]}
    """
    error_ids = data.get("error_ids", [])
    if not error_ids:
        raise HTTPException(status_code=400, detail="error_ids é obrigatório")
    
    from services.system_error_logger import system_error_logger
    count = await system_error_logger.mark_as_read(error_ids)
    return {"success": True, "marked_count": count}


@router.post("/system-logs/{error_id}/resolve")
async def resolve_system_error(
    error_id: str,
    data: dict = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca um erro como resolvido.
    
    Body (opcional): {"notes": "Corrigido em versão X"}
    """
    data = data or {}
    notes = data.get("notes")
    
    from services.system_error_logger import system_error_logger
    success = await system_error_logger.mark_as_resolved(
        error_id=error_id,
        resolved_by=user.get("email", "admin"),
        notes=notes
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Erro não encontrado")
    
    return {"success": True, "message": "Erro marcado como resolvido"}


@router.post("/system-logs/bulk-resolve")
async def bulk_resolve_system_errors(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca múltiplos erros como resolvidos em massa.
    
    Body: {"error_ids": ["id1", "id2", ...]}
    """
    error_ids = data.get("error_ids", [])
    
    if not error_ids:
        raise HTTPException(status_code=400, detail="Nenhum ID fornecido")
    
    from services.system_error_logger import system_error_logger
    resolved_count = await system_error_logger.bulk_mark_as_resolved(
        error_ids=error_ids,
        resolved_by=user.get("email", "admin")
    )
    
    return {
        "success": True, 
        "resolved_count": resolved_count,
        "message": f"{resolved_count} erros marcados como resolvidos"
    }


@router.post("/system-logs/resolve-all")
async def resolve_all_system_errors(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca TODOS os erros não resolvidos como resolvidos.
    Útil para limpar o painel de erros depois de uma manutenção.
    """
    from services.system_error_logger import system_error_logger
    resolved_count = await system_error_logger.resolve_all_unresolved(
        resolved_by=user.get("email", "admin")
    )
    
    return {
        "success": True,
        "resolved_count": resolved_count,
        "message": f"Todos os {resolved_count} erros foram marcados como resolvidos"
    }


@router.delete("/system-logs/cleanup")
async def cleanup_old_system_logs(
    days: int = 90,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove logs antigos (mais de N dias)."""
    from services.system_error_logger import system_error_logger
    count = await system_error_logger.cleanup_old_errors(days)
    return {"success": True, "deleted_count": count}



# ============== DATABASE INDEX MANAGEMENT ==============

@router.get("/db/indexes")
async def get_database_indexes(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Lista todos os índices de todas as colecções principais.
    Útil para diagnóstico de problemas de índices duplicados.
    """
    from services.db_indexes import get_index_stats
    stats = await get_index_stats(db)
    return {"success": True, "indexes": stats}


# ============== AI IMPORT LOGS (Item 3 - Outros erros/melhorias) ==============

@router.get("/ai-import-logs")
async def get_ai_import_logs(
    page: int = 1,
    limit: int = 50,
    status: str = None,
    days: int = 7,
    client_name: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de importação massiva IA para integração no menu de Logs do sistema.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - status: Filtrar por estado (success, error, warning)
    - days: Últimos N dias (default 7)
    - client_name: Filtrar por nome de cliente
    """
    skip = (page - 1) * limit
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    query = {"timestamp": {"$gte": cutoff_date}}
    
    if status == "error":
        query["resolved"] = False
    elif status == "success":
        query["resolved"] = True
    
    if client_name:
        query["client_name"] = {"$regex": client_name, "$options": "i"}
    
    # Buscar erros de importação
    errors = await db.import_errors.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
    
    # Contagem total
    total = await db.import_errors.count_documents(query)
    
    # Estatísticas rápidas
    stats = {
        "total_errors": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}}),
        "unresolved": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}, "resolved": False}),
        "resolved": await db.import_errors.count_documents({"timestamp": {"$gte": cutoff_date}, "resolved": True}),
    }
    
    # Formatar logs para UI
    formatted_logs = []
    for error in errors:
        formatted_logs.append({
            "id": error.get("id"),
            "timestamp": error.get("timestamp"),
            "severity": "error" if not error.get("resolved") else "info",
            "component": "ai_bulk_import",
            "error_type": error.get("document_type", "import_error"),
            "message": error.get("error", ""),
            "details": {
                "client_name": error.get("client_name"),
                "filename": error.get("filename"),
                "folder_name": error.get("folder_name"),
                "matching_details": error.get("matching_details")
            },
            "resolved": error.get("resolved", False),
            "user_email": error.get("user_email")
        })
    
    return {
        "logs": formatted_logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit
        },
        "stats": stats
    }


@router.post("/ai-import-logs/{log_id}/resolve")
async def resolve_ai_import_log(
    log_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca um log de importação como resolvido.
    """
    result = await db.import_errors.update_one(
        {"id": log_id},
        {
            "$set": {
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get("email", "admin")
            }
        }
    )
    
    # Também actualizar na colecção ai_import_logs
    await db.ai_import_logs.update_one(
        {"id": log_id},
        {
            "$set": {
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": user.get("email", "admin")
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return {"success": True, "message": "Log marcado como resolvido"}


@router.post("/ai-import-logs/bulk-resolve")
async def bulk_resolve_ai_import_logs(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Marca múltiplos logs de importação como resolvidos em massa.
    
    Body:
    - log_ids: Lista de IDs a resolver
    """
    log_ids = data.get("log_ids", [])
    if not log_ids:
        raise HTTPException(status_code=400, detail="Nenhum ID fornecido")
    
    now = datetime.now(timezone.utc).isoformat()
    resolved_by = user.get("email", "admin")
    
    # Actualizar na colecção ai_import_logs
    result = await db.ai_import_logs.update_many(
        {"id": {"$in": log_ids}, "resolved": {"$ne": True}},
        {
            "$set": {
                "resolved": True,
                "resolved_at": now,
                "resolved_by": resolved_by
            }
        }
    )
    
    # Também actualizar na colecção import_errors (legacy)
    await db.import_errors.update_many(
        {"id": {"$in": log_ids}},
        {
            "$set": {
                "resolved": True,
                "resolved_at": now,
                "resolved_by": resolved_by
            }
        }
    )
    
    return {
        "success": True,
        "resolved_count": result.modified_count,
        "message": f"{result.modified_count} logs marcados como resolvidos"
    }


@router.get("/ai-import-logs-v2/grouped")
async def get_ai_import_logs_grouped(
    days: int = 7,
    status: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de importação IA agrupados por cliente.
    Mostra resumo de sucesso/erro por cliente.
    
    Query params:
    - days: Últimos N dias (default 7)
    - status: Filtrar por estado (success, error, all)
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    match_stage = {"timestamp": {"$gte": cutoff_date}}
    if status == "error":
        match_stage["status"] = "error"
    elif status == "success":
        match_stage["status"] = "success"
    
    # Agregar por cliente
    pipeline = [
        {"$match": match_stage},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$client_name",
            "total_docs": {"$sum": 1},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "error_count": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
            "fields_updated": {"$sum": "$fields_count"},
            "last_import": {"$first": "$timestamp"},
            "logs": {"$push": {
                "id": "$id",
                "status": "$status",
                "filename": "$filename",
                "document_type": "$document_type",
                "timestamp": "$timestamp",
                "fields_count": "$fields_count",
                "error": "$error",
                "resolved": "$resolved"
            }}
        }},
        {"$sort": {"last_import": -1}},
        {"$project": {
            "client_name": "$_id",
            "total_docs": 1,
            "success_count": 1,
            "error_count": 1,
            "fields_updated": 1,
            "last_import": 1,
            "logs": {"$slice": ["$logs", 50]},  # Limitar a 50 logs por cliente
            "_id": 0
        }}
    ]
    
    groups = await db.ai_import_logs.aggregate(pipeline).to_list(100)
    
    # Estatísticas gerais
    stats = {
        "total_clients": len(groups),
        "total_docs": sum(g["total_docs"] for g in groups),
        "total_success": sum(g["success_count"] for g in groups),
        "total_errors": sum(g["error_count"] for g in groups),
        "total_fields": sum(g["fields_updated"] for g in groups)
    }
    
    return {
        "groups": groups,
        "stats": stats
    }


# ============== AI IMPORT LOGS V2 - Com categorização de dados ==============

@router.get("/ai-import-logs-v2")
async def get_ai_import_logs_v2(
    page: int = 1,
    limit: int = 50,
    status: str = None,
    days: int = 7,
    client_name: str = None,
    document_type: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém logs de importação IA com dados categorizados.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 50)
    - status: Filtrar por estado (success, error, partial, all)
    - days: Últimos N dias (default 7)
    - client_name: Filtrar por nome de cliente
    - document_type: Filtrar por tipo de documento (cc, irs, recibo_vencimento, etc.)
    
    Returns:
    - logs: Lista de logs com dados categorizados
    - stats: Estatísticas de sucesso/erro
    - pagination: Info de paginação
    """
    skip = (page - 1) * limit
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Query base
    query = {"created_at": {"$gte": cutoff_date}}
    
    if status == "error":
        query["status"] = "error"
    elif status == "success":
        query["status"] = "success"
    elif status == "partial":
        query["status"] = "partial"
    
    if client_name:
        query["client_name"] = {"$regex": client_name, "$options": "i"}
    
    if document_type:
        query["documents.document_type"] = document_type
    
    # Buscar logs
    logs = await db.ai_import_logs.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(None)
    
    # Contagem total
    total = await db.ai_import_logs.count_documents(query)
    
    # Estatísticas
    base_query = {"created_at": {"$gte": cutoff_date}}
    stats = {
        "total": await db.ai_import_logs.count_documents(base_query),
        "success": await db.ai_import_logs.count_documents({**base_query, "status": "success"}),
        "error": await db.ai_import_logs.count_documents({**base_query, "status": "error"}),
        "partial": await db.ai_import_logs.count_documents({**base_query, "status": "partial"}),
        "total_documents": 0,
        "success_documents": 0,
        "error_documents": 0,
    }
    
    # Contar documentos processados
    pipeline = [
        {"$match": base_query},
        {"$group": {
            "_id": None, 
            "total_docs": {"$sum": "$total_documents"},
            "success_docs": {"$sum": "$success_count"},
            "error_docs": {"$sum": "$error_count"}
        }}
    ]
    agg_result = await db.ai_import_logs.aggregate(pipeline).to_list(1)
    if agg_result:
        stats["total_documents"] = agg_result[0].get("total_docs", 0)
        stats["success_documents"] = agg_result[0].get("success_docs", 0)
        stats["error_documents"] = agg_result[0].get("error_docs", 0)
    
    # Taxa de sucesso
    if stats["total_documents"] > 0:
        stats["success_rate"] = round(stats["success_documents"] / stats["total_documents"] * 100, 1)
    else:
        stats["success_rate"] = 0
    
    return {
        "logs": logs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1
        },
        "stats": stats
    }


@router.get("/ai-import-logs-v2/{log_id}")
async def get_ai_import_log_detail(
    log_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém detalhes de um log de importação específico.
    Inclui dados categorizados por tabs.
    """
    log = await db.ai_import_logs.find_one(
        {"id": log_id},
        {"_id": 0}
    )
    
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    
    return log


@router.post("/db/indexes/repair")
async def repair_database_indexes(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Remove índices antigos/incorretos e recria os correctos.
    Use quando houver erros de duplicate key em índices.
    """
    from services.db_indexes import cleanup_deprecated_indexes, create_indexes
    
    # Primeiro, limpar índices problemáticos
    cleanup_results = await cleanup_deprecated_indexes(db)
    
    # Depois, garantir que os índices correctos existem
    create_results = await create_indexes(db)
    
    return {
        "success": True,
        "cleanup": cleanup_results,
        "indexes": create_results
    }


@router.delete("/db/indexes/{collection}/{index_name}")
async def drop_specific_index(
    collection: str,
    index_name: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Remove um índice específico de uma colecção.
    Use com cuidado - apenas para índices problemáticos.
    """
    allowed_collections = ["properties", "processes", "users", "tasks", "leads"]
    if collection not in allowed_collections:
        raise HTTPException(status_code=400, detail=f"Colecção não permitida. Use: {allowed_collections}")
    
    if index_name == "_id_":
        raise HTTPException(status_code=400, detail="Não pode remover o índice _id_")
    
    try:
        coll = db[collection]
        existing = await coll.index_information()
        
        if index_name not in existing:
            raise HTTPException(status_code=404, detail=f"Índice '{index_name}' não existe em '{collection}'")
        
        await coll.drop_index(index_name)
        return {"success": True, "message": f"Índice '{index_name}' removido de '{collection}'"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover índice: {str(e)}")



# ============== CLEANUP ENDPOINTS ==============

@router.delete("/cleanup/jobs")
async def cleanup_old_jobs(
    days: int = Query(default=7, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Remove jobs de background antigos (concluídos ou falhados).
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = await db.background_jobs.delete_many({
        "completed_at": {"$lt": cutoff},
        "status": {"$in": ["completed", "failed"]}
    })
    
    return {"success": True, "deleted_count": result.deleted_count}


@router.delete("/cleanup/error-logs")
async def cleanup_old_error_logs(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Remove logs de erro antigos.
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = await db.system_error_logs.delete_many({
        "timestamp": {"$lt": cutoff}
    })
    
    return {"success": True, "deleted_count": result.deleted_count}



# ============== MONITORIZAÇÃO DE JOBS ==============

@router.get("/jobs/health")
async def get_jobs_health(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Verifica o estado dos jobs em background.
    Detecta jobs travados (em execução há muito tempo).
    """
    from datetime import timedelta
    
    # Definir thresholds
    stuck_threshold_minutes = 30  # Job é considerado travado após 30 minutos
    
    # Buscar jobs recentes
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(hours=24)  # Últimas 24 horas
    
    # Buscar AI import logs (jobs de importação)
    ai_import_logs = await db.ai_import_logs.find(
        {"start_time": {"$gte": cutoff_time.isoformat()}},
        {"_id": 0}
    ).sort("start_time", -1).to_list(100)
    
    # Analisar jobs
    running_jobs = []
    stuck_jobs = []
    completed_jobs = []
    failed_jobs = []
    
    for log in ai_import_logs:
        status = log.get("status", "").lower()
        start_time_str = log.get("start_time")
        
        if status in ["completed", "success", "done"]:
            completed_jobs.append(log)
        elif status in ["failed", "error"]:
            failed_jobs.append(log)
        elif status in ["processing", "running", "in_progress"]:
            # Verificar se está travado
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    duration_minutes = (now - start_time).total_seconds() / 60
                    
                    if duration_minutes > stuck_threshold_minutes:
                        stuck_jobs.append({
                            **log,
                            "duration_minutes": round(duration_minutes, 1)
                        })
                    else:
                        running_jobs.append({
                            **log,
                            "duration_minutes": round(duration_minutes, 1)
                        })
                except Exception:
                    running_jobs.append(log)
            else:
                running_jobs.append(log)
    
    # Calcular estatísticas
    total_jobs = len(ai_import_logs)
    success_rate = (len(completed_jobs) / total_jobs * 100) if total_jobs > 0 else 0
    
    return {
        "timestamp": now.isoformat(),
        "healthy": len(stuck_jobs) == 0,
        "stats": {
            "total_24h": total_jobs,
            "running": len(running_jobs),
            "stuck": len(stuck_jobs),
            "completed": len(completed_jobs),
            "failed": len(failed_jobs),
            "success_rate": round(success_rate, 1)
        },
        "stuck_jobs": stuck_jobs,
        "running_jobs": running_jobs,
        "alerts": [
            {
                "type": "stuck_job",
                "message": f"Job travado há {job.get('duration_minutes', 0)} minutos: {job.get('job_id', 'N/A')}",
                "job_id": job.get("job_id"),
                "severity": "warning"
            }
            for job in stuck_jobs
        ]
    }


@router.post("/jobs/cancel/{job_id}")
async def cancel_stuck_job(
    job_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Cancela/marca um job travado como falhado.
    """
    # Actualizar log para failed
    result = await db.ai_import_logs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "cancelled",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "cancelled_by": user.get("id"),
            "cancelled_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    return {
        "success": True,
        "job_id": job_id,
        "message": "Job cancelado com sucesso"
    }





# ============== CLIENT REGISTRATIONS MANAGEMENT ==============

@router.get("/client-registrations")
async def list_client_registrations(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    source: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Lista registos de clientes do formulário público.
    
    Query params:
    - page: Página (default 1)
    - limit: Items por página (default 20)
    - search: Pesquisar por nome, email ou NIF
    - status: Filtrar por estado do processo
    - source: Filtrar por origem (public_form, manual, etc.)
    """
    query = {}
    
    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_email": {"$regex": search, "$options": "i"}},
            {"personal_data.nif": {"$regex": search, "$options": "i"}}
        ]
    
    if status:
        query["status"] = status
    
    if source:
        query["source"] = source
    
    skip = (page - 1) * limit
    
    total = await db.processes.count_documents(query)
    
    processes = await db.processes.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "registrations": processes,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@router.get("/client-registrations/{process_id}")
async def get_client_registration(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém detalhes de um registo de cliente.
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    return {"registration": process}


@router.put("/client-registrations/{process_id}")
async def update_client_registration(
    process_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Atualiza dados de um registo de cliente.
    
    Permite editar:
    - Dados pessoais (personal_data)
    - Dados do 2º titular (titular2_data)
    - Dados do imóvel (real_estate_data)
    - Dados financeiros (financial_data)
    - Informações de contacto (client_name, client_email, client_phone)
    """
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    update_data = {}
    
    # Campos simples
    if "client_name" in data:
        update_data["client_name"] = data["client_name"]
    if "client_email" in data:
        update_data["client_email"] = data["client_email"]
    if "client_phone" in data:
        update_data["client_phone"] = data["client_phone"]
    if "second_client_name" in data:
        update_data["second_client_name"] = data["second_client_name"]
    
    # Campos aninhados
    if "personal_data" in data:
        # Manter dados existentes e actualizar apenas os fornecidos
        existing_personal = process.get("personal_data", {})
        existing_personal.update(data["personal_data"])
        update_data["personal_data"] = existing_personal
    
    if "titular2_data" in data:
        existing_titular2 = process.get("titular2_data", {}) or {}
        existing_titular2.update(data["titular2_data"])
        update_data["titular2_data"] = existing_titular2
    
    if "real_estate_data" in data:
        existing_realestate = process.get("real_estate_data", {}) or {}
        existing_realestate.update(data["real_estate_data"])
        update_data["real_estate_data"] = existing_realestate
    
    if "financial_data" in data:
        existing_financial = process.get("financial_data", {}) or {}
        existing_financial.update(data["financial_data"])
        update_data["financial_data"] = existing_financial
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("email", "admin")
    
    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    # Log da alteração
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": "Dados do registo editados pelo admin",
        "field": "registration_edit",
        "old_value": None,
        "new_value": list(update_data.keys()),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    return {
        "success": True,
        "message": "Registo atualizado com sucesso",
        "registration": updated
    }


@router.delete("/client-registrations/{process_id}")
async def delete_client_registration(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Elimina um registo de cliente.
    
    NOTA: Esta ação é irreversível e remove todos os dados do processo.
    """
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    
    # Guardar log antes de eliminar
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user.get("name", "Admin"),
        "action": f"Registo eliminado: {process.get('client_name', 'N/A')} ({process.get('client_email', 'N/A')})",
        "field": "registration_delete",
        "old_value": process.get("client_name"),
        "new_value": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Eliminar processo
    await db.processes.delete_one({"id": process_id})
    
    # Eliminar histórico associado
    await db.history.delete_many({"process_id": process_id})
    
    # Eliminar RGPDs associados
    await db.rgpd_requests.delete_many({"process_id": process_id})
    
    return {
        "success": True,
        "message": "Registo eliminado com sucesso"
    }


@router.get("/client-registrations/stats/summary")
async def get_client_registrations_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém estatísticas de registos de clientes.
    """
    # Total de registos
    total = await db.processes.count_documents({})
    
    # Registos por origem
    by_source = await db.processes.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    # Registos por estado
    by_status = await db.processes.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]).to_list(50)
    
    # Registos hoje
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.processes.count_documents({
        "created_at": {"$gte": today.isoformat()}
    })
    
    # Registos esta semana
    week_start = today - timedelta(days=today.weekday())
    week_count = await db.processes.count_documents({
        "created_at": {"$gte": week_start.isoformat()}
    })
    
    # Registos este mês
    month_start = today.replace(day=1)
    month_count = await db.processes.count_documents({
        "created_at": {"$gte": month_start.isoformat()}
    })
    
    return {
        "total": total,
        "today": today_count,
        "this_week": week_count,
        "this_month": month_count,
        "by_source": {item["_id"] or "unknown": item["count"] for item in by_source},
        "by_status": {item["_id"] or "unknown": item["count"] for item in by_status}
    }


# ============== AUDIT LOGS (O18) ==============

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(100, le=500),
    skip: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    entity: Optional[str] = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """O18 - Lista de audit logs para acções críticas do sistema."""
    query = {}
    if action:
        query["action"] = action
    if entity:
        query["entity"] = entity
    
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(length=limit)
    total = await db.audit_logs.count_documents(query)
    
    return {"logs": logs, "total": total, "limit": limit, "skip": skip}


# ============== STALE PROCESSES STATS ==============

@router.get("/stale-processes")
async def get_stale_processes(
    days: int = Query(14, ge=1, le=90),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Obter estatísticas de processos sem atualização.
    Retorna processos agrupados por nível de urgência.
    """
    now = datetime.now(timezone.utc)
    final_statuses = [
        "concluido", "concluidos", "cancelado", "recusado", 
        "desistiu", "desistencia", "desistencias", "desistência",
        "escritura_feita", "arquivado", "perdido", "eliminado"
    ]
    
    cutoff = (now - timedelta(days=days)).isoformat()
    
    stale = await db.processes.find({
        "status": {"$nin": final_statuses},
        "$or": [
            {"updated_at": {"$lte": cutoff}},
            {"updated_at": {"$exists": False}, "created_at": {"$lte": cutoff}}
        ]
    }, {"_id": 0, "id": 1, "client_name": 1, "status": 1, "consultor_name": 1, 
        "mediador_name": 1, "updated_at": 1, "created_at": 1}).to_list(500)
    
    # Calcular dias desde última actualização
    results = []
    for p in stale:
        last = p.get("updated_at") or p.get("created_at", "")
        try:
            last_date = datetime.fromisoformat(last.replace('Z', '+00:00'))
            days_since = (now - last_date).days
        except (ValueError, TypeError, AttributeError):
            days_since = days
        
        results.append({
            "id": p["id"],
            "client_name": p.get("client_name", ""),
            "status": p.get("status", ""),
            "consultor_name": p.get("consultor_name", ""),
            "mediador_name": p.get("mediador_name", ""),
            "days_since_update": days_since,
            "urgency": "critical" if days_since > 21 else "high" if days_since > 14 else "medium"
        })
    
    results.sort(key=lambda x: x["days_since_update"], reverse=True)
    
    return {
        "total": len(results),
        "critical": len([r for r in results if r["urgency"] == "critical"]),
        "high": len([r for r in results if r["urgency"] == "high"]),
        "medium": len([r for r in results if r["urgency"] == "medium"]),
        "processes": results[:100]
    }


@router.get("/team-performance")
async def get_team_performance(
    start_date: Optional[str] = Query(None, description="Data de início (YYYY-MM-DD). Por defeito, há 7 dias"),
    end_date: Optional[str] = Query(None, description="Data de fim (YYYY-MM-DD). Por defeito, hoje"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obter estatísticas de desempenho da equipa para um dado período.
    Retorna a lista de colaboradores com: processos avançados,
    tarefas concluídas, tarefas atrasadas e tarefas pendentes.

    Reutiliza a lógica de agregação do analytics_service.
    """
    from services.analytics_service import generate_weekly_team_report

    now = datetime.now(timezone.utc)

    # Parse dates with defaults
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="end_date inválido. Use YYYY-MM-DD")
    else:
        end_dt = now

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="start_date inválido. Use YYYY-MM-DD")
    else:
        start_dt = end_dt - timedelta(days=7)

    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="start_date deve ser anterior a end_date")

    report = await generate_weekly_team_report(db, period_start=start_dt, period_end=end_dt)

    return {
        "period_start": report["period_start"],
        "period_end": report["period_end"],
        "summary": report["summary"],
        "users": report["users"],
    }


# ============== PROD → DEV DATABASE SYNC (RGPD SANITIZATION) ==============

# In-memory lock to prevent concurrent sync operations
_sync_in_progress = False
_sync_result_cache = {"result": None, "timestamp": None}


class SyncDatabaseRequest(BaseModel):
    """
    Modelo para a requisição de restauro de BD a partir de backup.

    Nota: prod_url e prod_db_name já não são necessários pois a fonte
    é o backup automático no S3 (não a BD de Produção diretamente).
    Mantidos para compatibilidade backward (são ignorados).
    """
    prod_url: Optional[str] = None   # Ignorado (legado — mantido para compatibilidade)
    prod_db_name: Optional[str] = None  # Ignorado (legado)
    dev_url: Optional[str] = None
    dev_db_name: Optional[str] = None


@router.get("/sync-database/status")
async def get_sync_status(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém o estado da última sincronização Prod → Dev.
    """
    return {
        "in_progress": _sync_in_progress,
        "last_result": _sync_result_cache["result"],
        "last_timestamp": _sync_result_cache["timestamp"],
    }


@router.post("/sync-database")
async def sync_database(
    request: SyncDatabaseRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Restaura a base de dados de Desenvolvimento a partir do backup de Produção (S3).

    Arquitetura (sem carga no servidor de Produção):
        S3 Backup (ZIP) → Download → Extract JSON → Coleções _temp → Sanitize RGPD
        → Validar integridade → Swap para coleções reais → Cleanup

    SEGURANÇA:
    - Só funciona se ENVIRONMENT != "production" (403 em produção)
    - Só pode ser executado por admin (role = admin)
    - Executa em background (BackgroundTasks) para evitar timeouts
    - FALHA SEGURA: Dev DB NÃO é modificada se o backup estiver corrompido

    Anonimização RGPD aplicada:
    - clients: email → dev_client_{id}@powercell.dev, NIF → falso válido, phone → baralhado
    - processes: remove links S3/AWS, limpa campos financeiros ultra-sensíveis
    - properties: remove links S3, limpa dados financeiros, arredonda coordenadas
    - users: mantém emails e passwords reais para login, anonimiza dados pessoais
    """
    # Nota: `global` não é necessário aqui pois apenas lemos _sync_in_progress.
    # A escrita (atribuição) acontece dentro de _execute_restore() que já
    # declara o seu próprio `global`.

    # ─── SEGURANÇA 1: Bloquear em produção ───
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment in ("production", "prod"):
        logger.warning(f"Tentativa de restore em PRODUÇÃO bloqueada por utilizador {user.get('email')}")
        raise HTTPException(
            status_code=403,
            detail="Este endpoint NÃO pode ser executado em produção. Ação bloqueada por segurança."
        )

    # ─── SEGURANÇA 2: Apenas admin ───
    if user.get("role") != UserRole.ADMIN:
        logger.warning(f"Tentativa de restore por não-admin bloqueada: {user.get('email')}")
        raise HTTPException(
            status_code=403,
            detail="Apenas o administrador pode executar esta operação."
        )

    # ─── PREVENIR CONCORRÊNCIA ───
    if _sync_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Já existe um restauro em curso. Aguarde a conclusão."
        )

    # ─── RESOLVER URI DEV ───
    dev_url = request.dev_url or os.getenv("DEV_MONGO_URL")
    dev_db_name = request.dev_db_name or os.getenv("DEV_DB_NAME")

    if not dev_url or not dev_db_name:
        raise HTTPException(
            status_code=400,
            detail="URL e nome da BD de Desenvolvimento são obrigatórios. Defina DEV_MONGO_URL/DEV_DB_NAME ou envie no body."
        )

    # ─── REGISTAR AUDIT LOG ───
    await _audit_log(
        "restore_dev_from_backup",
        "database",
        "restore",
        user,
        {
            "mode": "backup_restore",
            "dev_db": dev_db_name,
            "environment": environment,
            "anonymization": True,
            "source": "s3_backup",
        }
    )

    # ─── EXECUTAR EM BACKGROUND ───
    async def _execute_restore():
        """Executa o restauro da BD de desenvolvimento a partir do backup S3.

        Esta função interna é executada em background (via BackgroundTasks)
        e coordena todo o pipeline de restauro:

        1. Download do backup ZIP mais recente do S3.
        2. Extração dos ficheiros JSON de cada coleção.
        3. Sanitização RGPD (anonimização de dados pessoais).
        4. Validação de integridade dos dados.
        5. Escrita para coleções temporárias (_temp).
        6. Swap atómico das coleções temporárias para as reais.
        7. Limpeza das coleções temporárias.

        Porquê em background: o restauro pode demorar vários minutos
        dependendo do tamanho da base de dados. Executar de forma
        síncrona causaria timeout no FastAPI.

        Garantias de segurança:
        - FALHA SEGURA: se qualquer etapa falhar, a BD de dev não é
          modificada (usa coleções _temp como intermediário).
        - Regista resultado (sucesso ou erro) em ``_sync_result_cache``.
        - Sempre define ``_sync_in_progress = False`` no finally.

        Raises:
            Exception: Qualquer erro durante o restauro é capturado e
                registado em ``_sync_result_cache`` sem propagar.
        """
        global _sync_in_progress, _sync_result_cache
        _sync_in_progress = True
        try:
            from scripts.restore_dev_from_backup import run_restore
            result = await run_restore(dev_url, dev_db_name)
            _sync_result_cache = {"result": result, "timestamp": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            logger.error(f"Erro crítico no restore Dev from backup: {e}", exc_info=True)
            _sync_result_cache = {
                "result": {
                    "success": False,
                    "error": str(e),
                    "total_documents": 0,
                    "mode": "backup_restore",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            _sync_in_progress = False

    background_tasks.add_task(_execute_restore)

    return {
        "success": True,
        "message": "Restauro a partir de backup iniciado em background. Use GET /admin/sync-database/status para acompanhar.",
        "details": {
            "mode": "backup_restore",
            "source": "s3_latest_backup",
            "dev_db": dev_db_name,
            "anonymization": True,
            "fail_safe": True,
            "environment": environment,
            "started_by": user.get("email"),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    }


# ============== USER EMAIL CONFIG MANAGEMENT (ADMIN) ==============

@router.get("/users/{user_id}/email-config")
async def admin_get_user_email_config(
    user_id: str,
    admin: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obter configuração de email de um utilizador alvo (Admin/CEO).

    SEGURANÇA: Nunca devolve a password real — apenas has_password: true.
    O admin pode VER que uma password existe, mas nunca a lê em plain-text.

    Args:
        user_id: ID do utilizador alvo.
        admin: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: Configuração de email (sem password).

    Raises:
        HTTPException(404): Se utilizador não encontrado.
    """
    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1, "name": 1, "email": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    config = target.get("email_config")
    if not config:
        return {
            "is_configured": False,
            "email_address": None,
            "imap_server": None,
            "imap_port": None,
            "smtp_server": None,
            "smtp_port": None,
            "has_password": False,
            "target_user": {
                "id": user_id,
                "name": target.get("name"),
                "email": target.get("email"),
            },
        }

    return {
        "is_configured": config.get("is_configured", False),
        "email_address": config.get("email_address"),
        "imap_server": config.get("imap_server"),
        "imap_port": config.get("imap_port", 993),
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 465),
        "has_password": bool(config.get("encrypted_password")),
        "has_google_oauth": bool(config.get("google_refresh_token")),
        "auth_method": (
            "google_oauth" if config.get("google_refresh_token")
            else "imap_smtp" if config.get("encrypted_password")
            else "none"
        ),
        "google_email": config.get("google_email"),
        "target_user": {
            "id": user_id,
            "name": target.get("name"),
            "email": target.get("email"),
        },
    }


@router.post("/users/{user_id}/email-config")
async def admin_set_user_email_config(
    user_id: str,
    config: "EmailConfigCreate",
    admin: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Definir configuração de email IMAP/SMTP de um utilizador alvo (Admin/CEO).

    SEGURANÇA: A password fornecida pelo admin é encriptada com Fernet
    (via services/encryption.py) ANTES de ser guardada na base de dados.
    O admin nunca visualiza a password existente — apenas pode definir uma nova.

    Se a password for omitida/vazia e o utilizador já tem uma configuração,
    a password existente é mantida.

    Args:
        user_id: ID do utilizador alvo.
        config: Dados de configuração (EmailConfigCreate).
        admin: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: success, message.

    Raises:
        HTTPException(404): Se utilizador não encontrado.
        HTTPException(500): Se erro ao guardar.
    """
    from models.email_config import EmailConfigCreate
    from services.encryption import encryption_service

    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "name": 1, "email_config": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # Se não foi fornecida password, manter a existente (se houver)
    encrypted_password = ""
    existing_config = target.get("email_config", {})
    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)
    elif existing_config.get("encrypted_password"):
        encrypted_password = existing_config["encrypted_password"]

    email_config = {
        "email_address": config.email_address.strip().lower(),
        "imap_server": config.imap_server.strip(),
        "imap_port": config.imap_port,
        "smtp_server": config.smtp_server.strip(),
        "smtp_port": config.smtp_port,
        "encrypted_password": encrypted_password,
        "is_configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Preservar campos Google OAuth existentes (não os apagar ao guardar IMAP)
    if existing_config.get("google_refresh_token"):
        email_config["google_refresh_token"] = existing_config["google_refresh_token"]
    if existing_config.get("google_access_token"):
        email_config["google_access_token"] = existing_config["google_access_token"]
    if existing_config.get("google_email"):
        email_config["google_email"] = existing_config["google_email"]
    if existing_config.get("auth_method"):
        email_config["auth_method"] = existing_config["auth_method"]
    if existing_config.get("oauth_connected_at"):
        email_config["oauth_connected_at"] = existing_config["oauth_connected_at"]

    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"email_config": email_config}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Erro ao guardar configuração")

    # Audit log
    await _audit_log(
        "user_email_config_set",
        "user",
        user_id,
        admin,
        {
            "email_address": config.email_address.strip().lower(),
            "imap_server": config.imap_server.strip(),
            "smtp_server": config.smtp_server.strip(),
        }
    )

    return {
        "success": True,
        "message": f"Configuração de email guardada para {target.get('name', user_id)}",
        "is_configured": True,
    }


@router.post("/users/{user_id}/email-config/test")
async def admin_test_user_email_config(
    user_id: str,
    admin: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Testar ligação de email de um utilizador alvo (Admin/CEO) — Smart.

    Se o utilizador tem Google OAuth → testa Gmail API.
    Se tem password IMAP/SMTP → testa IMAP/SMTP.

    Args:
        user_id: ID do utilizador alvo.
        admin: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: success, auth_method, gmail_api_connected/imap_connected/smtp_connected, error.

    Raises:
        HTTPException(404): Se utilizador não encontrado.
        HTTPException(400): Se configuração de email não existe.
    """
    from services.gmail_oauth import test_connection_smart

    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1, "name": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    config = target.get("email_config")
    if not config:
        raise HTTPException(
            status_code=400,
            detail=f"Configuração de email não encontrada para {target.get('name', user_id)}"
        )

    result = await test_connection_smart(config, user_id)
    result["target_user"] = {
        "id": user_id,
        "name": target.get("name"),
    }
    return result


@router.post("/sync-process-emails")
async def sync_process_emails(user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))):
    """
    Migração: sincroniza personal_data.email → client_email em todos os processos.

    Corrige processos onde o email existe em personal_data.email mas client_email
    está vazio ou diferente. Também gera/actualiza o email_hash.
    """
    from services.encryption import generate_email_hash
    from utils.input_sanitization import sanitize_email

    pipeline = [
        {"$match": {
            "status": {"$ne": "eliminado"},
            "$or": [
                {"personal_data.email": {"$exists": True, "$ne": "", "$ne": None}},
                {"personal_data.email_hash": {"$exists": True, "$ne": None}},
            ]
        }},
        {"$project": {"id": 1, "client_email": 1, "personal_data.email": 1, "personal_data.email_hash": 1}}
    ]

    processes = await db.processes.aggregate(pipeline).to_list(length=None)
    updated = 0
    errors = 0

    for proc in processes:
        try:
            pd_email = (proc.get("personal_data") or {}).get("email", "")
            pd_email = str(pd_email).strip() if pd_email else ""
            current = str(proc.get("client_email", "") or "").strip()

            update_fields = {}

            # Sync email se personal_data.email tem valor e client_email está vazio/diferente
            if pd_email and pd_email != current:
                sanitized = sanitize_email(pd_email)
                if sanitized:
                    update_fields["client_email"] = sanitized

            # Garantir que email_hash existe
            if pd_email:
                email_hash = generate_email_hash(pd_email.lower().strip())
                if email_hash:
                    existing_hash = (proc.get("personal_data") or {}).get("email_hash")
                    if existing_hash != email_hash:
                        update_fields["personal_data.email_hash"] = email_hash

            if update_fields:
                await db.processes.update_one(
                    {"id": proc["id"]},
                    {"$set": update_fields}
                )
                updated += 1
        except Exception as e:
            errors += 1
            logger.error(f"Erro ao sincronizar email do processo {proc.get('id')}: {e}")

    return {
        "success": True,
        "total_checked": len(processes),
        "updated": updated,
        "errors": errors,
        "message": f"Sincronização concluída: {updated} processos actualizados de {len(processes)} verificados."
    }

