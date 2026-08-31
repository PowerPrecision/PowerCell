"""Workflow statuses + S3 CORS diagnostic (admin).

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

from services.s3_storage import s3_service


async def run_get_workflow_statuses(user: dict):
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


async def run_create_workflow_status(data: WorkflowStatusCreate, user: dict):
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
        # PACOTE BS — Dynamic Workflow Purpose Flags
        # Persistidas como None se não fornecidas (fallback ativo no move_process_kanban)
        "is_active": data.is_active,
        "trigger_finance": data.trigger_finance,
        "trigger_countdown": data.trigger_countdown,
        "trigger_property_check": data.trigger_property_check,
        "trigger_deed_reminder": data.trigger_deed_reminder,
    }

    await db.workflow_statuses.insert_one(status_doc)
    return WorkflowStatusResponse(**{k: v for k, v in status_doc.items() if k != "_id"})


async def run_update_workflow_status(status_id: str, data: WorkflowStatusUpdate, user: dict):
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
    # PACOTE BS — Dynamic Workflow Purpose Flags
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.trigger_finance is not None:
        update_data["trigger_finance"] = data.trigger_finance
    if data.trigger_countdown is not None:
        update_data["trigger_countdown"] = data.trigger_countdown
    if data.trigger_property_check is not None:
        update_data["trigger_property_check"] = data.trigger_property_check
    if data.trigger_deed_reminder is not None:
        update_data["trigger_deed_reminder"] = data.trigger_deed_reminder

    if update_data:
        await db.workflow_statuses.update_one({"id": status_id}, {"$set": update_data})

    updated = await db.workflow_statuses.find_one({"id": status_id}, {"_id": 0})
    return WorkflowStatusResponse(**updated)


async def run_delete_workflow_status(status_id: str, user: dict):
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


async def run_fix_duplicate_workflow_statuses(user: dict):
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


async def run_s3_cors_diagnostic(user: dict, force_fix: bool = False, request: Request = None):
    """
    Diagnóstico e fix da configuração CORS do bucket S3.

    GET: Lê a config CORS atual e reporta estado.
    POST: Força a aplicação da config CORS correcta.

    O browser bloqueia uploads diretos ao S3 se não houver CORS configurado.
    """
    from services.s3_storage import AWS_BUCKET_NAME, AWS_REGION
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


async def run_migrate_portal_labels(user: dict):
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


