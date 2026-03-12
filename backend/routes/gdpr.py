"""
====================================================================
GDPR ROUTES - CREDITOIMO
====================================================================
Endpoints para gestão de conformidade GDPR.

Apenas administradores podem aceder a estes endpoints.

Endpoints:
- GET  /api/gdpr/statistics     - Estatísticas de conformidade
- POST /api/gdpr/anonymize      - Anonimizar processo específico
- POST /api/gdpr/batch          - Executar anonimização em lote
- GET  /api/gdpr/export/{id}    - Exportar dados pessoais
- GET  /api/gdpr/audit          - Consultar log de auditoria
====================================================================
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import require_roles, get_current_user
from services.gdpr import (
    anonymize_process_data,
    anonymize_user_data,
    run_anonymization_batch,
    export_personal_data,
    get_gdpr_statistics,
    find_processes_for_anonymization,
    gdpr_config
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gdpr", tags=["GDPR Compliance"])


# ====================================================================
# MODELS
# ====================================================================
class AnonymizeRequest(BaseModel):
    """Request para anonimização."""
    process_id: Optional[str] = None
    user_id: Optional[str] = None
    dry_run: bool = False


class BatchAnonymizeRequest(BaseModel):
    """Request para anonimização em lote."""
    retention_days: Optional[int] = None
    batch_size: int = 100
    dry_run: bool = True  # Default: dry run por segurança


# ====================================================================
# ENDPOINTS
# ====================================================================
@router.get("/statistics")
async def get_statistics(
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém estatísticas de conformidade GDPR.
    
    Retorna:
    - Total de processos
    - Processos anonimizados
    - Processos elegíveis para anonimização
    - Taxa de anonimização
    - Acções de auditoria recentes
    """
    stats = await get_gdpr_statistics()
    return {
        "success": True,
        "data": stats
    }


@router.get("/eligible")
async def get_eligible_processes(
    retention_days: int = Query(default=None, description="Dias de retenção"),
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Lista processos elegíveis para anonimização.
    
    Útil para preview antes de executar anonimização.
    """
    processes = await find_processes_for_anonymization(retention_days, limit)
    
    return {
        "success": True,
        "count": len(processes),
        "retention_days": retention_days or gdpr_config.retention_period_days,
        "processes": processes
    }


@router.post("/anonymize")
async def anonymize_single(
    request: AnonymizeRequest,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Anonimiza dados de um processo ou utilizador específico.
    
    ⚠️ ATENÇÃO: Esta acção é irreversível!
    
    Use dry_run=true primeiro para verificar o que será anonimizado.
    """
    if not request.process_id and not request.user_id:
        raise HTTPException(400, "Especifique process_id ou user_id")
    
    results = {}
    
    if request.process_id:
        results["process"] = await anonymize_process_data(
            request.process_id, 
            request.dry_run
        )
    
    if request.user_id:
        results["user"] = await anonymize_user_data(
            request.user_id, 
            request.dry_run
        )
    
    # Log de auditoria (quem fez a acção)
    if not request.dry_run:
        await db.gdpr_audit.insert_one({
            "action": "manual_anonymize",
            "process_id": request.process_id,
            "user_id": request.user_id,
            "performed_by": current_user.get("id"),
            "performed_by_email": current_user.get("email"),
            "timestamp": datetime.now(timezone.utc)
        })
    
    return {
        "success": True,
        "dry_run": request.dry_run,
        "results": results
    }


@router.post("/batch")
async def anonymize_batch(
    request: BatchAnonymizeRequest,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Executa anonimização em lote.
    
    ⚠️ ATENÇÃO: Esta acção é irreversível quando dry_run=false!
    
    Por segurança, dry_run=true é o default.
    Execute primeiro com dry_run para verificar o que será anonimizado.
    """
    if not request.dry_run:
        # Confirmação adicional para execução real
        logger.warning(
            f"[GDPR] Anonimização em lote iniciada por {current_user.get('email')} "
            f"(batch_size={request.batch_size})"
        )
    
    result = await run_anonymization_batch(
        retention_days=request.retention_days,
        dry_run=request.dry_run,
        batch_size=request.batch_size
    )
    
    # Log de auditoria
    await db.gdpr_audit.insert_one({
        "action": "batch_anonymize",
        "dry_run": request.dry_run,
        "batch_size": request.batch_size,
        "retention_days": request.retention_days or gdpr_config.retention_period_days,
        "processed": result.get("processed", 0),
        "succeeded": result.get("succeeded", 0),
        "performed_by": current_user.get("id"),
        "performed_by_email": current_user.get("email"),
        "timestamp": datetime.now(timezone.utc)
    })
    
    return {
        "success": True,
        **result
    }


@router.get("/export/{process_id}")
async def export_data(
    process_id: str,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Exporta dados pessoais de um processo.
    
    Implementa o direito à portabilidade (RGPD Artigo 20).
    
    Retorna todos os dados pessoais em formato JSON estruturado.
    """
    data = await export_personal_data(process_id=process_id)
    
    if not data.get("data"):
        raise HTTPException(404, "Processo não encontrado")
    
    return {
        "success": True,
        **data
    }


@router.get("/audit")
async def get_audit_log(
    days: int = Query(default=30, le=365),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Consulta o log de auditoria GDPR.
    
    Mostra todas as acções de anonimização, exportação e acesso a dados.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = {"timestamp": {"$gte": cutoff}}
    if action:
        query["action"] = action
    
    audit_entries = await db.gdpr_audit.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {
        "success": True,
        "count": len(audit_entries),
        "period_days": days,
        "entries": audit_entries
    }


@router.get("/config")
async def get_gdpr_config(
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém configuração actual do GDPR.
    """
    return {
        "success": True,
        "config": {
            "retention_period_days": gdpr_config.retention_period_days,
            "eligible_statuses": gdpr_config.eligible_statuses,
            "batch_size": gdpr_config.batch_size,
            "dry_run_mode": gdpr_config.dry_run
        }
    }
