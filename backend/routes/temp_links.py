"""
Rotas de links temporários — thin FastAPI stubs.

Logic in services/temp_link_api_*.py (do **not** overwrite
services/temp_link_service.py).

Staff create/list/cancel live alongside public /public/{token}* paths;
path order: /create and /process/{id} before /{link_id}; public paths
are distinct prefixes so order vs staff is flexible.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks

from models.auth import UserRole
from models.temp_link import TempLinkResponse
from services.auth import get_current_user, require_roles
from services.temp_link_api_staff import (
    run_create_temp_link,
    run_list_process_temp_links,
    run_cancel_temp_link,
    run_delete_temp_link,
)
from services.temp_link_api_public import (
    run_get_public_link_info,
    run_upload_via_temp_link,
    run_download_via_temp_link,
    run_download_all_via_temp_link,
    run_list_temp_link_files,
)

router = APIRouter(prefix="/temp-links", tags=["Temporary Links"])


@router.post("/create", response_model=TempLinkResponse)
async def create_temp_link(
    process_id: str = Form(...),
    link_type: str = Form(...),
    expires_in_hours: int = Form(default=72),
    max_uses: int = Form(default=1),
    description: Optional[str] = Form(default=None),
    file_paths: Optional[str] = Form(default=None),
    notify_email: Optional[str] = Form(default="true"),
    base_url: Optional[str] = Form(default=None),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))
):
    return await run_create_temp_link(
        process_id=process_id,
        link_type=link_type,
        user=user,
        expires_in_hours=expires_in_hours,
        max_uses=max_uses,
        description=description,
        file_paths=file_paths,
        notify_email=notify_email,
        base_url=base_url,
    )


@router.get("/process/{process_id}")
async def list_process_temp_links(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_list_process_temp_links(process_id, user)


@router.post("/{link_id}/cancel")
async def cancel_temp_link(
    link_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))
):
    return await run_cancel_temp_link(link_id, user)


@router.delete("/{link_id}")
async def delete_temp_link(
    link_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    return await run_delete_temp_link(link_id, user)


@router.get("/public/{token}")
async def get_public_link_info(token: str):
    return await run_get_public_link_info(token)


@router.post("/public/{token}/upload")
async def upload_via_temp_link(
    token: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    return await run_upload_via_temp_link(token, files, background_tasks)


@router.get("/public/{token}/download/{file_index}")
async def download_via_temp_link(
    token: str,
    file_index: int = 0
):
    return await run_download_via_temp_link(token, file_index)


@router.get("/public/{token}/download-all")
async def download_all_via_temp_link(token: str):
    return await run_download_all_via_temp_link(token)


@router.get("/public/{token}/files")
async def list_temp_link_files(token: str):
    return await run_list_temp_link_files(token)
