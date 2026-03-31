"""
Rotas de Auditoria (Audit Trail)
Endpoints para consulta, exportação e gestão de registos de auditoria.
Apenas acessíveis a administradores e CEO.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from models.auth import UserRole
from services.auth import require_roles
from services.audit_trail_service import (
    get_audit_trail,
    get_audit_stats,
    export_audit_trail,
    cleanup_old_records,
)

router = APIRouter(prefix="/audit", tags=["Audit Trail"])
logger = logging.getLogger(__name__)


@router.get("/trail")
async def list_audit_trail(
    request: Request,
    process_id: str = Query(None, description="Filtrar por ID do processo"),
    user_id: str = Query(None, description="Filtrar por ID do utilizador"),
    action_type: str = Query(None, description="Filtrar por tipo de acção (texto parcial)"),
    source: str = Query(None, description="Filtrar por origem (web, api, ai_automation, email)"),
    date_from: str = Query(None, description="Data inicial (ISO 8601)"),
    date_to: str = Query(None, description="Data final (ISO 8601)"),
    ai_suggested: bool = Query(None, description="Filtrar apenas sugestões de IA"),
    page: int = Query(1, ge=1, description="Número da página"),
    page_size: int = Query(50, ge=1, le=200, description="Itens por página"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """
    Listar registos de auditoria com paginação e filtros.
    Apenas administradores e CEO podem aceder.
    """
    try:
        result = await get_audit_trail(
            process_id=process_id,
            user_id=user_id,
            action_type=action_type,
            source=source,
            date_from=date_from,
            date_to=date_to,
            ai_suggested=ai_suggested,
            page=page,
            page_size=page_size,
        )
        return result
    except Exception as e:
        logger.error(f"Erro ao consultar audit trail: {e}")
        raise HTTPException(status_code=500, detail="Erro ao consultar registos de auditoria")


@router.get("/stats")
async def audit_statistics(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """
    Obter estatísticas de auditoria para o dashboard.
    """
    try:
        stats = await get_audit_stats()
        return stats
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de auditoria: {e}")
        raise HTTPException(status_code=500, detail="Erro ao obter estatísticas")


@router.get("/export")
async def export_audit(
    process_id: str = Query(None, description="Filtrar por ID do processo"),
    user_id: str = Query(None, description="Filtrar por ID do utilizador"),
    source: str = Query(None, description="Filtrar por origem"),
    date_from: str = Query(None, description="Data inicial (ISO 8601)"),
    date_to: str = Query(None, description="Data final (ISO 8601)"),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO])),
):
    """
    Exportar registos de auditoria como ficheiro CSV.
    """
    try:
        csv_content = await export_audit_trail(
            process_id=process_id,
            user_id=user_id,
            source=source,
            date_from=date_from,
            date_to=date_to,
        )

        # Gerar nome de ficheiro com data actual
        from datetime import datetime, timezone
        filename = f"audit_trail_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )
    except Exception as e:
        logger.error(f"Erro ao exportar audit trail: {e}")
        raise HTTPException(status_code=500, detail="Erro ao exportar registos de auditoria")


@router.post("/cleanup")
async def trigger_cleanup(
    days: int = Query(None, description="Dias de retenção (usa config se omitido)"),
    user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    """
    Limpar registos de auditoria antigos (apenas admin).
    """
    try:
        deleted_count = await cleanup_old_records(days=days)
        logger.info(f"Cleanup de audit trail executado por {user.get('email')}: {deleted_count} registos eliminados")
        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"{deleted_count} registos eliminados com sucesso",
        }
    except Exception as e:
        logger.error(f"Erro no cleanup de audit trail: {e}")
        raise HTTPException(status_code=500, detail="Erro ao limpar registos de auditoria")
