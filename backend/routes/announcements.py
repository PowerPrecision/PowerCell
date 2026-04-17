"""
====================================================================
ROTAS DE ANÚNCIOS - MURAL DA EQUIPA
====================================================================
Endpoints para gestão de anúncios do quadro de informação geral.
Qualquer utilizador autenticado pode ler e criar anúncios.

Autor: PowerCell Development Team
====================================================================
"""

import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from database import db
from services.auth import get_current_user
from models.announcement import AnnouncementCreate, AnnouncementResponse


router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.get("", response_model=List[AnnouncementResponse])
async def get_announcements(
    user: dict = Depends(get_current_user)
):
    """
    Obter os últimos 50 anúncios ordenados por data de criação (descendente).

    Qualquer utilizador autenticado pode listar anúncios.
    """
    announcements = await db.announcements.find(
        {},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    return announcements


@router.post("", response_model=AnnouncementResponse, status_code=201)
async def create_announcement(
    announcement: AnnouncementCreate,
    user: dict = Depends(get_current_user)
):
    """
    Criar um novo anúncio no mural da equipa.

    O conteúdo é sanitizado (remoção de espaços em branco no início/fim)
    e limitado a 2000 caracteres. Qualquer utilizador autenticado pode
    publicar anúncios.
    """
    content = announcement.content.strip()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="O conteúdo do anúncio não pode estar vazio"
        )

    if len(content) > 2000:
        raise HTTPException(
            status_code=400,
            detail="O conteúdo do anúncio não pode exceder 2000 caracteres"
        )

    now = datetime.now(timezone.utc)

    new_announcement = {
        "id": str(uuid.uuid4()),
        "content": content,
        "author_id": user["id"],
        "author_name": user.get("name", user.get("email", "Desconhecido")),
        "author_role": user.get("role"),
        "created_at": now.isoformat()
    }

    await db.announcements.insert_one(new_announcement)

    return new_announcement
