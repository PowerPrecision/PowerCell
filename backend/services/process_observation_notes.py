"""PACOTE DU — Feed de notas (observações) do processo.

Guarda `observation_notes` como array de {text, created_at, user_id, user_name}
e regista cada entrada no histórico (ícones da Timeline).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException
from pydantic import BaseModel, Field

from database import db


class ObservationNoteCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def build_observation_note(text: str, user: dict) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "text": text.strip(),
        "created_at": now,
        "user_id": user.get("id"),
        "user_name": user.get("name") or user.get("email") or "Utilizador",
    }


def coalesce_observation_notes(process: dict | None) -> list[dict]:
    """Devolve o feed: array persistido, ou uma nota legado a partir da string."""
    process = process or {}
    notes = process.get("observation_notes")
    if isinstance(notes, list) and notes:
        return notes
    legacy = str(process.get("observations") or process.get("notes") or "").strip()
    if not legacy:
        return []
    return [{
        "id": "legacy",
        "text": legacy,
        "created_at": process.get("updated_at") or process.get("created_at"),
        "user_id": None,
        "user_name": None,
    }]


def append_observation_note(process: dict, note: dict) -> list[dict]:
    """Acrescenta `note` ao array, preservando texto legado uma única vez."""
    existing = process.get("observation_notes")
    if isinstance(existing, list) and existing:
        return list(existing) + [note]

    new_notes: list[dict] = []
    legacy = str(process.get("observations") or process.get("notes") or "").strip()
    if legacy and legacy != note.get("text"):
        new_notes.append({
            "id": str(uuid.uuid4()),
            "text": legacy,
            "created_at": process.get("created_at"),
            "user_id": None,
            "user_name": None,
        })
    new_notes.append(note)
    return new_notes


async def run_add_observation_note(
    process_id: str,
    data: ObservationNoteCreate,
    user: dict,
    *,
    can_view_fn: Callable,
    can_edit_fn: Callable,
    log_history_fn: Callable,
    populate_fn: Callable,
    decrypt_fn: Callable,
) -> dict:
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    if not can_view_fn(user, process):
        raise HTTPException(status_code=403, detail="Acesso negado")

    can_edit, reason = can_edit_fn(user, process)
    if not can_edit:
        raise HTTPException(status_code=403, detail=reason or "Sem permissão para editar")

    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="O texto da nota é obrigatório")

    note = build_observation_note(text, user)
    new_notes = append_observation_note(process, note)

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {
            "observation_notes": new_notes,
            "observations": text,
            "notes": text,
            "updated_at": note["created_at"],
        }},
    )

    await log_history_fn(
        process_id,
        user,
        "Adicionou observação",
        "observation_notes",
        None,
        text[:500],
    )

    updated = await db.processes.find_one({"id": process_id}, {"_id": 0})
    updated = decrypt_fn(updated)
    return await populate_fn(updated)
