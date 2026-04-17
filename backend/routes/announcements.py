"""
<<<<<<< HEAD
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
=======
Rotas de Anúncios — Mural da Equipa (Feed Interno)

PORQUÊ: Permite comunicação assíncrona entre membros da equipa.
Qualquer membro da equipa (staff) pode publicar, dar gosto e marcar como lido.

ENDPOINTS:
- GET  /api/announcements       → Listar últimas 50 mensagens (DESC)
- POST /api/announcements       → Publicar nova mensagem
- POST /api/announcements/{id}/like  → Toggle like (adicionar/remover)
- POST /api/announcements/{id}/read  → Marcar como lido pelo utilizador
- DELETE /api/announcements/{id}     → Eliminar mensagem (autor ou admin)
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.announcement import AnnouncementCreate, AnnouncementResponse
from services.auth import get_current_user, require_staff
from utils.input_sanitization import sanitize_string
>>>>>>> 0e005d2 (feat: add likes and read receipts to team mural)


router = APIRouter(prefix="/announcements", tags=["Announcements"])


<<<<<<< HEAD
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
=======
# ============== CRUD ROUTES ==============

@router.get("", response_model=List[AnnouncementResponse])
async def get_announcements(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_staff())
):
    """Listar os últimos anúncios do mural da equipa (DESC by created_at)."""
    announcements = await db.announcements.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)

    return [
        AnnouncementResponse(
            id=a["id"],
            content=a["content"],
            author_id=a["author_id"],
            author_name=a["author_name"],
            created_at=a["created_at"],
            likes=a.get("likes", []),
            read_by=a.get("read_by", []),
        )
        for a in announcements
    ]


@router.post("", response_model=AnnouncementResponse)
async def create_announcement(
    data: AnnouncementCreate,
    user: dict = Depends(require_staff())
):
    """Publicar uma nova mensagem no mural da equipa."""
    announcement_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    announcement_doc = {
        "id": announcement_id,
        "content": sanitize_string(data.content, max_length=2000),
        "author_id": user["id"],
        "author_name": user["name"],
        "created_at": now,
        "likes": [],
        "read_by": [],
    }

    await db.announcements.insert_one(announcement_doc)

    return AnnouncementResponse(**{k: v for k, v in announcement_doc.items() if k != "_id"})


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """Eliminar uma mensagem do mural (apenas autor ou admin)."""
    announcement = await db.announcements.find_one({"id": announcement_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    if announcement["author_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Só pode eliminar as suas próprias mensagens")

    await db.announcements.delete_one({"id": announcement_id})
    return {"message": "Mensagem eliminada"}


# ============== INTERACTION ROUTES ==============

@router.post("/{announcement_id}/like", response_model=AnnouncementResponse)
async def toggle_like(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """
    Toggle like: se o utilizador já deu gosto, remove; caso contrário, adiciona.
    """
    announcement = await db.announcements.find_one({"id": announcement_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    user_id = user["id"]
    current_likes = announcement.get("likes", [])

    if user_id in current_likes:
        # Remover gosto
        current_likes.remove(user_id)
    else:
        # Adicionar gosto
        current_likes.append(user_id)

    await db.announcements.update_one(
        {"id": announcement_id},
        {"$set": {"likes": current_likes}}
    )

    return AnnouncementResponse(
        id=announcement["id"],
        content=announcement["content"],
        author_id=announcement["author_id"],
        author_name=announcement["author_name"],
        created_at=announcement["created_at"],
        likes=current_likes,
        read_by=announcement.get("read_by", []),
    )


@router.post("/{announcement_id}/read")
async def mark_as_read(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """
    Marcar mensagem como lida pelo utilizador atual.
    Adiciona o ID do utilizador à lista read_by se ainda não lá estiver.
    """
    announcement = await db.announcements.find_one({"id": announcement_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    user_id = user["id"]
    current_read_by = announcement.get("read_by", [])

    if user_id not in current_read_by:
        current_read_by.append(user_id)
        await db.announcements.update_one(
            {"id": announcement_id},
            {"$set": {"read_by": current_read_by}}
        )

    return {"message": "Marcada como lida", "read_count": len(current_read_by)}


@router.get("/readers/{announcement_id}")
async def get_readers(
    announcement_id: str,
    user: dict = Depends(require_staff())
):
    """
    Obter lista de nomes dos utilizadores que leram uma mensagem.
    Retorna array de strings com os nomes.
    """
    announcement = await db.announcements.find_one(
        {"id": announcement_id},
        {"_id": 0, "read_by": 1}
    )
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    read_by_ids = announcement.get("read_by", [])
    if not read_by_ids:
        return {"readers": []}

    # Buscar nomes dos utilizadores
    readers_cursor = db.users.find(
        {"id": {"$in": read_by_ids}},
        {"_id": 0, "id": 1, "name": 1}
    )
    readers = await readers_cursor.to_list(len(read_by_ids))

    reader_names = [r["name"] for r in readers if r.get("name")]
    return {"readers": reader_names}
>>>>>>> 0e005d2 (feat: add likes and read receipts to team mural)
