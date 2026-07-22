"""
====================================================================
ROTAS DE STORAGE GENÉRICO — thin FastAPI stubs
====================================================================
Logic in services/storage_api_*.py.
Do **not** overwrite s3_storage.py / storage_service.py.
====================================================================
"""
from fastapi import APIRouter, Depends

from routes.auth import get_current_user
from services.storage_api_status import run_get_storage_status
from services.storage_api_folder import (
    run_get_process_folder_url,
    run_save_process_folder_url,
    run_delete_process_folder_url,
)
from services.storage_api_checklist import (
    run_generate_document_checklist,
    run_get_document_checklist,
)

router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/status")
async def get_storage_status(user: dict = Depends(get_current_user)):
    """Obter status do armazenamento configurado."""
    return await run_get_storage_status()


@router.get("/process/{process_id}/folder-url")
async def get_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter URL da pasta do cliente no storage configurado."""
    return await run_get_process_folder_url(process_id)


@router.put("/process/{process_id}/folder-url")
async def save_process_folder_url(
    process_id: str,
    folder_url: str,
    user: dict = Depends(get_current_user)
):
    """Guardar o link da pasta do cliente no processo."""
    return await run_save_process_folder_url(process_id, folder_url)


@router.delete("/process/{process_id}/folder-url")
async def delete_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Remover o link da pasta do processo."""
    return await run_delete_process_folder_url(process_id)


@router.post("/process/{process_id}/checklist")
async def generate_document_checklist(
    process_id: str,
    files: list[str],
    user: dict = Depends(get_current_user)
):
    """Gerar checklist de documentos baseada nos ficheiros fornecidos."""
    return await run_generate_document_checklist(process_id, files)


@router.get("/process/{process_id}/checklist")
async def get_document_checklist(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter checklist de documentos guardada para um processo."""
    return await run_get_document_checklist(process_id)
