"""Announcements like / read / readers handlers.

Extraído de `routes/announcements.py`.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db
from models.announcement import AnnouncementResponse


async def run_toggle_like(announcement_id: str, user: dict):
    announcement = await db.announcements.find_one({"id": announcement_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    user_id = user["id"]
    current_likes = announcement.get("likes", [])

    if user_id in current_likes:
        current_likes.remove(user_id)
    else:
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


async def run_mark_as_read(announcement_id: str, user: dict):
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


async def run_get_readers(announcement_id: str):
    announcement = await db.announcements.find_one(
        {"id": announcement_id},
        {"_id": 0, "read_by": 1}
    )
    if not announcement:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    read_by_ids = announcement.get("read_by", [])
    if not read_by_ids:
        return {"readers": []}

    readers_cursor = db.users.find(
        {"id": {"$in": read_by_ids}},
        {"_id": 0, "id": 1, "name": 1}
    )
    readers = await readers_cursor.to_list(len(read_by_ids))
    reader_names = [r["name"] for r in readers if r.get("name")]
    return {"readers": reader_names}
