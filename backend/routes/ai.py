"""
AI Document Analysis routes — thin FastAPI stubs.

Logic in services/ai_api_*.py.
Do **not** overwrite ai_document.py / ai_document_analyzer.py /
ai_page_analyzer.py / ai_usage_tracker.py / ai_improvement_agent.py.
"""
from fastapi import APIRouter, BackgroundTasks, Depends

from models.auth import UserRole
from services.auth import get_current_user, require_roles
from services.ai_api_analyze import (
    AnalyzeDocumentRequest,
    AnalyzeOneDriveDocumentRequest,
    run_analyze_document,
    run_analyze_onedrive_document,
    run_get_supported_documents,
)
from services.ai_api_reset import (
    ResetClientDataRequest,
    run_reset_client_data,
)
from services.ai_api_async import (
    AsyncAnalyzeDocumentRequest,
    run_analyze_document_async,
)
from services.ai_api_bulk import (
    BulkAnalysisRequest,
    run_bulk_analysis_async,
)

router = APIRouter(prefix="/ai", tags=["AI Document Analysis"])


@router.post("/analyze-document")
async def analyze_document(
    request: AnalyzeDocumentRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO])),
):
    return await run_analyze_document(request, user)


@router.post("/analyze-onedrive-document")
async def analyze_onedrive_document(
    request: AnalyzeOneDriveDocumentRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO])),
):
    return await run_analyze_onedrive_document(request, user)


@router.get("/supported-documents")
async def get_supported_documents(user: dict = Depends(get_current_user)):
    return await run_get_supported_documents(user)


@router.post("/reset-client-data")
async def reset_client_data(
    request: ResetClientDataRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_reset_client_data(request, user)


@router.post("/analyze-document-async")
async def analyze_document_async(
    request: AsyncAnalyzeDocumentRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO])),
):
    return await run_analyze_document_async(request, background_tasks, user)


@router.post("/bulk-analysis-async")
async def bulk_analysis_async(
    request: BulkAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    return await run_bulk_analysis_async(request, background_tasks, user)
