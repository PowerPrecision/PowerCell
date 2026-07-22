"""
OneDrive Routes - thin FastAPI stubs.

Logic in services/onedrive_*.py.
Do **not** overwrite services/onedrive.py (Graph OAuth core).
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user
from services.onedrive_status import run_get_onedrive_status
from services.onedrive_folder_url import (
    run_get_process_folder_url,
    run_remove_process_folder_url,
    run_save_process_folder_url,
)
from services.onedrive_checklist import (
    run_generate_document_checklist,
    run_get_document_checklist,
)
from services.onedrive_files import run_get_client_files_by_name
from services.onedrive_links import (
    LinkCreate,
    LinkUpdate,
    run_add_process_link,
    run_delete_process_link,
    run_get_process_links,
    run_update_process_link,
)

router = APIRouter(prefix="/onedrive", tags=["OneDrive"])


@router.get("/status")
async def get_onedrive_status(user: dict = Depends(get_current_user)):
    """Verificar estado da integração OneDrive."""
    return await run_get_onedrive_status(user)


@router.get("/process/{process_id}/folder-url")
async def get_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter URL para abrir a pasta do cliente no OneDrive."""
    return await run_get_process_folder_url(process_id, user)


@router.put("/process/{process_id}/folder-url")
async def save_process_folder_url(
    process_id: str,
    folder_url: str,
    user: dict = Depends(get_current_user),
):
    """Guardar o link da pasta do cliente no processo."""
    return await run_save_process_folder_url(process_id, folder_url, user)


@router.delete("/process/{process_id}/folder-url")
async def remove_process_folder_url(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Remover o link da pasta do processo."""
    return await run_remove_process_folder_url(process_id, user)


@router.post("/process/{process_id}/checklist")
async def generate_document_checklist(
    process_id: str,
    files: list[str],
    user: dict = Depends(get_current_user),
):
    """Gerar checklist de documentos baseada nos ficheiros fornecidos."""
    return await run_generate_document_checklist(process_id, files, user)


@router.get("/process/{process_id}/checklist")
async def get_document_checklist(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter checklist de documentos guardada para um processo."""
    return await run_get_document_checklist(process_id, user)


@router.get("/files/{client_name}")
async def get_client_files_by_name(
    client_name: str,
    subfolder: str = "",
    user: dict = Depends(get_current_user),
):
    """Listar ficheiros de um cliente pelo nome (S3)."""
    return await run_get_client_files_by_name(client_name, subfolder, user)


@router.get("/links/{process_id}")
async def get_process_links(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter todos os links de um processo."""
    return await run_get_process_links(process_id, user)


@router.post("/links/{process_id}")
async def add_process_link(
    process_id: str,
    link_data: LinkCreate,
    user: dict = Depends(get_current_user),
):
    """Adicionar um novo link a um processo."""
    return await run_add_process_link(process_id, link_data, user)


@router.delete("/links/{process_id}/{link_id}")
async def delete_process_link(
    process_id: str,
    link_id: str,
    user: dict = Depends(get_current_user),
):
    """Remover um link de um processo."""
    return await run_delete_process_link(process_id, link_id, user)


@router.put("/links/{process_id}/{link_id}")
async def update_process_link(
    process_id: str,
    link_id: str,
    link_data: LinkUpdate,
    user: dict = Depends(get_current_user),
):
    """Actualizar um link existente."""
    return await run_update_process_link(process_id, link_id, link_data, user)
