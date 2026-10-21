"""
«LOG DA IA» DO PROCESSO — `GET /api/processes/{process_id}/ai-log`
================================================================
Rota própria (os routers de processos estão acima do tecto dos stubs finos). Só leitura.
Staff apenas; a fronteira de rede vem ANTES de tudo (404 igual ao de «não existe»).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from services.auth import require_staff
from services.process_ai_log_api import run_get_process_ai_log
from services.process_scope_guard import exigir_processo_no_ambito

router = APIRouter(
    prefix="/processes",
    tags=["Processes"],
    dependencies=[Depends(exigir_processo_no_ambito)],
)


@router.get("/{process_id}/ai-log")
async def get_process_ai_log(
    request: Request,
    process_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    estado: Optional[str] = Query(None),
    user: dict = Depends(require_staff()),
):
    """Timeline das acções da IA sobre os documentos do processo (mais recente primeiro)."""
    return await run_get_process_ai_log(
        request, process_id, user, pagina=page, por_pagina=size, estado=estado
    )
