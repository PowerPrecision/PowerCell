"""
====================================================================
AI BULK ANALYSIS ROUTES — thin FastAPI stubs
====================================================================
Logic in services/ai_bulk_*.py. Shared package helpers remain under
routes/ai_bulk/ (cache, jobs, matching, utils, constants).
Background job endpoints: routes/ai_bulk/background_jobs.py.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from services.auth import get_current_user
from services.ai_bulk_models import (
    AggregatedFileResult,
    AggregatedFinishResponse,
    AggregatedSessionRequest,
    AggregatedSessionResponse,
    ImportSessionRequest,
    ImportSessionResponse,
    SingleAnalysisResult,
    UpdateSessionRequest,
)
from services.ai_bulk_sessions import (
    run_finish_aggregated_session,
    run_finish_import_session,
    run_get_aggregated_session_status,
    run_start_aggregated_session,
    run_start_import_session,
    run_update_import_session,
)
from services.ai_bulk_analyze import (
    run_analyze_file_aggregated,
    run_analyze_single_file,
)
from services.ai_bulk_import_errors import (
    run_get_import_errors,
    run_resolve_import_error,
)
from services.ai_bulk_clients import (
    run_check_client_exists,
    run_diagnose_client_data,
    run_get_analyzed_documents,
    run_get_clients_list,
    run_suggest_clients,
)
from services.ai_bulk_cache_ops import (
    run_add_nif_mapping_manual,
    run_clear_duplicate_cache,
    run_clear_nif_cache,
    run_get_nif_cache_stats,
    run_get_pending_reviews,
)

# Re-export for routes/ai_bulk/__init__.py importlib getattr + external callers
from routes.ai_bulk.matching import normalize_text_for_matching  # noqa: F401
from routes.ai_bulk.constants import (  # noqa: F401
    ERROR_AGGREGATION_SESSION_EXPIRED,
    ERROR_AGGREGATION_SESSION_NOT_FOUND,
    ERROR_SESSION_NOT_FOUND,
)

router = APIRouter(prefix="/ai/bulk", tags=["AI Bulk Analysis"])


@router.post("/import-session/start", response_model=ImportSessionResponse)
async def start_import_session(
    request: ImportSessionRequest,
    user: dict = Depends(get_current_user),
):
    """Iniciar uma sessão de importação em massa."""
    return await run_start_import_session(request, user)


@router.post("/import-session/{session_id}/update")
async def update_import_session(
    session_id: str,
    request: UpdateSessionRequest,
    user: dict = Depends(get_current_user),
):
    """Actualizar o progresso de uma sessão de importação."""
    return await run_update_import_session(session_id, request, user)


@router.post("/import-session/{session_id}/finish")
async def finish_import_session(
    session_id: str,
    success: bool = True,
    message: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Finalizar uma sessão de importação."""
    return await run_finish_import_session(session_id, user, success, message)


@router.post("/aggregated-session/start", response_model=AggregatedSessionResponse)
async def start_aggregated_session(
    request: AggregatedSessionRequest,
    user: dict = Depends(get_current_user),
):
    """Iniciar sessão de importação AGREGADA."""
    return await run_start_aggregated_session(request, user)


@router.post(
    "/aggregated-session/{session_id}/analyze",
    response_model=AggregatedFileResult,
    responses={
        404: {"description": ERROR_AGGREGATION_SESSION_NOT_FOUND},
        400: {"description": "Ficheiro rejeitado por validação de segurança"},
    },
)
async def analyze_file_aggregated(
    session_id: str,
    file: UploadFile = File(...),
    force_client_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    """Analisar ficheiro e AGREGAR dados (não salva ainda)."""
    return await run_analyze_file_aggregated(
        session_id, file, user, force_client_id,
    )


@router.post(
    "/aggregated-session/{session_id}/finish",
    response_model=AggregatedFinishResponse,
    responses={
        404: {"description": ERROR_AGGREGATION_SESSION_EXPIRED},
        500: {"description": "Erro ao finalizar importação"},
    },
)
async def finish_aggregated_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Finalizar sessão de importação AGREGADA."""
    return await run_finish_aggregated_session(session_id, user)


@router.get(
    "/aggregated-session/{session_id}/status",
    responses={404: {"description": ERROR_SESSION_NOT_FOUND}},
)
async def get_aggregated_session_status(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter estado da sessão de importação agregada."""
    return await run_get_aggregated_session_status(session_id, user)


@router.post("/analyze-single", response_model=SingleAnalysisResult)
async def analyze_single_file(
    file: UploadFile = File(...),
    force_client_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    """Analisar um único ficheiro."""
    return await run_analyze_single_file(file, user, force_client_id)


@router.get("/import-errors")
async def get_import_errors(
    limit: int = 100,
    document_type: Optional[str] = None,
    resolved: Optional[bool] = None,
    user: dict = Depends(get_current_user),
):
    """Obter lista de erros de importação."""
    return await run_get_import_errors(user, limit, document_type, resolved)


@router.post("/import-errors/{error_id}/resolve")
async def resolve_import_error(
    error_id: str,
    user: dict = Depends(get_current_user),
):
    """Marcar um erro de importação como resolvido."""
    return await run_resolve_import_error(error_id, user)


@router.get("/suggest-clients")
async def suggest_clients_endpoint(
    query: str,
    limit: int = 5,
    user: dict = Depends(get_current_user),
):
    """Retornar clientes similares para selecção manual."""
    return await run_suggest_clients(query, user, limit)


@router.get("/check-client")
async def check_client_exists(
    name: str,
    user: dict = Depends(get_current_user),
):
    """Verificar se um cliente existe pelo nome."""
    return await run_check_client_exists(name, user)


@router.get("/clients-list")
async def get_clients_list(user: dict = Depends(get_current_user)):
    """Obter lista de clientes para referência no upload."""
    return await run_get_clients_list(user)


@router.get("/diagnose-client/{client_name}")
async def diagnose_client_data(
    client_name: str,
    user: dict = Depends(get_current_user),
):
    """Diagnóstico de dados de um cliente."""
    return await run_diagnose_client_data(client_name, user)


@router.get("/analyzed-documents/{process_id}")
async def get_analyzed_documents(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Listar documentos já analisados para um processo."""
    return await run_get_analyzed_documents(process_id, user)


@router.post("/clear-duplicate-cache")
async def clear_duplicate_cache(user: dict = Depends(get_current_user)):
    """Limpar cache de documentos duplicados."""
    return await run_clear_duplicate_cache(user)


@router.get("/nif-cache/stats")
async def get_nif_cache_stats(user: dict = Depends(get_current_user)):
    """Obter estatísticas do cache de sessão NIF."""
    return await run_get_nif_cache_stats(user)


@router.post("/nif-cache/clear")
async def clear_nif_cache_endpoint(user: dict = Depends(get_current_user)):
    """Limpar todo o cache de sessão NIF."""
    return await run_clear_nif_cache(user)


@router.post("/nif-cache/add-mapping")
async def add_nif_mapping_manual(
    folder_name: str,
    nif: str,
    user: dict = Depends(get_current_user),
):
    """Adicionar mapeamento NIF → Cliente manualmente."""
    return await run_add_nif_mapping_manual(folder_name, nif, user)


@router.get("/pending-reviews")
async def get_pending_reviews(user: dict = Depends(get_current_user)):
    """Obter lista de processos com dados pendentes de revisão."""
    return await run_get_pending_reviews(user)


from routes.ai_bulk.background_jobs import router as background_jobs_router

router.include_router(background_jobs_router)
