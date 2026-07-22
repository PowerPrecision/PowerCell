"""
====================================================================
Rotas de Anúncios — thin FastAPI stubs
====================================================================
Logic in services/announcements_api_*.py.
Keep /readers/{id} before delete if needed; like/read are postfix.
====================================================================
"""
from typing import List

from fastapi import APIRouter, Depends, Query

from models.announcement import AnnouncementCreate, AnnouncementResponse
from services.auth import require_staff
from services.announcements_api_crud import (
    run_get_announcements,
    run_create_announcement,
    run_delete_announcement,
)
from services.announcements_api_interactions import (
    run_toggle_like,
    run_mark_as_read,
    run_get_readers,
)

router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.get("", response_model=List[AnnouncementResponse])
async def get_announcements(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_staff())
):
    """Listar os últimos anúncios do mural da equipa."""
    return await run_get_announcements(limit)


@router.post("", response_model=AnnouncementResponse)
async def create_announcement(
    data: AnnouncementCreate,
    user: dict = Depends(require_staff())
):
    """Publicar uma nova mensagem no mural da equipa."""
    return await run_create_announcement(data, user)


@router.get("/readers/{announcement_id}")
async def get_readers(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """Obter lista de nomes dos utilizadores que leram uma mensagem."""
    return await run_get_readers(announcement_id)


@router.post("/{announcement_id}/like", response_model=AnnouncementResponse)
async def toggle_like(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """Toggle like: se o utilizador já deu gosto, remove; caso contrário, adiciona."""
    return await run_toggle_like(announcement_id, user)


@router.post("/{announcement_id}/read")
async def mark_as_read(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """Marcar mensagem como lida pelo utilizador atual."""
    return await run_mark_as_read(announcement_id, user)


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """Eliminar uma mensagem do mural (apenas autor ou admin)."""
    return await run_delete_announcement(announcement_id, user)
