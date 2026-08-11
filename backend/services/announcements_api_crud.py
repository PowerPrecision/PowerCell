"""Announcements CRUD handlers.

Extraído de `routes/announcements.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.announcement import AnnouncementCreate, AnnouncementResponse
from utils.input_sanitization import sanitize_string


async def run_get_announcements(limit: int):
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


async def run_create_announcement(data: AnnouncementCreate, user: dict):
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


async def run_delete_announcement(announcement_id: str, user: dict):
    announcement = await db.announcements.find_one({"id": announcement_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    if announcement["author_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Só pode eliminar as suas próprias mensagens")

    await db.announcements.delete_one({"id": announcement_id})
    return {"message": "Mensagem eliminada"}
