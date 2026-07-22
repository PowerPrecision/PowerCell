"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - MAPEAMENTO DE STORAGE (S3) — thin stubs
====================================================================
Logic in services/admin_s3_*.py (NOT services/admin_storage.py — name collision
with this route module; see AGENTS.md).
Do not overwrite s3_storage.py / storage_service.py.
====================================================================
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, Query, Body, UploadFile, File, Form

from models.auth import UserRole
from services.auth import require_roles

from services.admin_s3_client_mappings import run_auto_map_client_s3_folders
from services.admin_s3_user_mappings import (
    run_get_user_s3_mappings,
    run_update_user_s3_mapping,
    run_get_user_s3_mapping,
)
from services.admin_s3_process_mappings import (
    run_get_process_s3_mappings,
    run_update_process_s3_mapping,
    run_fix_missing_client_names,
    run_batch_update_process_s3_mappings,
)
from services.admin_s3_explorer import (
    FILE_OPS_ROLES,
    FILE_VIEW_ROLES,
    S3RenameRequest,
    S3DeleteRequest,
    S3CreateFolderRequest,
    run_get_s3_folder_contents,
    run_s3_rename,
    run_s3_delete,
    run_s3_create_folder,
    run_s3_upload,
    run_s3_download,
)

router = APIRouter(prefix="/admin", tags=["Admin - Storage"])
logger = logging.getLogger(__name__)


# ============== ALIAS PARA RETROCOMPATIBILIDADE ==============
# O frontend usa "client-s3-mappings" mas o backend usa "process-s3-mappings"

@router.get("/client-s3-mappings")
async def get_client_s3_mappings_alias(
    search: str = Query(None),
    process_id: str = Query(None),
    s3_folder: str = Query(None),
    include_closed: bool = Query(False, description="Incluir processos concluídos e desistências"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Alias para process-s3-mappings (retrocompatibilidade)."""
    return await run_get_process_s3_mappings(
        search=search,
        status=None,
        has_mapping=None,
        include_closed=include_closed,
        include_deleted=False,
        page=page,
        limit=limit,
        user=user,
    )


@router.post("/client-s3-mappings")
async def update_client_s3_mapping_alias(
    process_id: str = Query(...),
    s3_folder: str = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Alias para process-s3-mappings (retrocompatibilidade)."""
    return await run_update_process_s3_mapping(
        process_id=process_id, s3_folder=s3_folder, user=user,
    )


@router.post("/client-s3-mappings/bulk")
async def batch_update_client_s3_mappings_alias(
    mappings: List[dict] = Body(...),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Alias para batch update (retrocompatibilidade)."""
    return await run_batch_update_process_s3_mappings(mappings=mappings, user=user)


@router.post("/client-s3-mappings/fix-missing-names")
async def fix_missing_client_names_alias(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Alias para fix-missing-names (retrocompatibilidade)."""
    return await run_fix_missing_client_names(user=user)


@router.post("/client-s3-mappings/auto-map")
async def auto_map_client_s3_folders(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_auto_map_client_s3_folders(user)


# ============== MAPEAMENTO UTILIZADORES-S3 ==============

@router.get("/user-s3-mappings")
async def get_user_s3_mappings(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_user_s3_mappings(user)


@router.post("/user-s3-mappings")
async def update_user_s3_mapping(
    user_id: str = Query(...),
    s3_folder: str = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_update_user_s3_mapping(user_id, s3_folder, user)


@router.get("/user-s3-mappings/{user_id}")
async def get_user_s3_mapping(
    user_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_user_s3_mapping(user_id, user)


# ============== MAPEAMENTO CLIENTES/PROCESSOS-S3 ==============

@router.get("/process-s3-mappings")
async def get_process_s3_mappings(
    search: str = Query(None, description="Pesquisar por nome ou email"),
    status: str = Query(None, description="Filtrar por status"),
    has_mapping: bool = Query(None, description="Filtrar por ter/não ter mapeamento"),
    include_closed: bool = Query(False, description="Incluir processos concluídos e desistências"),
    include_deleted: bool = Query(False, description="Incluir processos eliminados"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_get_process_s3_mappings(
        search=search,
        status=status,
        has_mapping=has_mapping,
        include_closed=include_closed,
        include_deleted=include_deleted,
        page=page,
        limit=limit,
        user=user,
    )


@router.post("/process-s3-mappings")
async def update_process_s3_mapping(
    process_id: str = Query(...),
    s3_folder: str = Query(None),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_update_process_s3_mapping(process_id, s3_folder, user)


@router.post("/process-s3-mappings/fix-missing-names")
async def fix_missing_client_names(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_fix_missing_client_names(user)


@router.post("/process-s3-mappings/batch")
async def batch_update_process_s3_mappings(
    mappings: List[dict] = Body(...),
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_batch_update_process_s3_mappings(mappings, user)


# ============== S3 FILE OPERATIONS ==============

@router.get("/s3-folder-contents")
async def get_s3_folder_contents(
    folder_path: str = Query("", description="Caminho da pasta S3 (vazio = raiz)"),
    user: dict = Depends(require_roles([
        UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
        UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO,
    ]))
):
    return await run_get_s3_folder_contents(folder_path, user)


@router.post("/s3-rename")
async def s3_rename(
    data: S3RenameRequest,
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    return await run_s3_rename(data, user)


@router.post("/s3-delete")
async def s3_delete(
    data: S3DeleteRequest,
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    return await run_s3_delete(data, user)


@router.post("/s3-create-folder")
async def s3_create_folder(
    data: S3CreateFolderRequest,
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    return await run_s3_create_folder(data, user)


@router.post("/s3-upload")
async def s3_upload(
    file: UploadFile = File(...),
    folder_path: str = Form(""),
    user: dict = Depends(require_roles(FILE_OPS_ROLES))
):
    return await run_s3_upload(file, folder_path, user)


@router.get("/s3-download")
async def s3_download(
    path: str = Query(..., description="Caminho S3 do ficheiro"),
    user: dict = Depends(require_roles(FILE_VIEW_ROLES))
):
    return await run_s3_download(path, user)
