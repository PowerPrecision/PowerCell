"""
====================================================================
Notas de voz do consultor — thin FastAPI stubs (Épico 7)
====================================================================
Lógica em `services/voice_note_api.py` e `services/voice_note_engine.py`.
====================================================================
"""
from fastapi import APIRouter, Depends, File, UploadFile

from services.auth import get_current_user
from services.voice_note_api import run_create_voice_note, run_list_voice_notes

router = APIRouter(tags=["Voice Notes"])


@router.post("/processes/{process_id}/voice-notes")
async def create_voice_note(
    process_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Recebe uma gravação e lança a transcrição + extracção em background."""
    return await run_create_voice_note(process_id, file, user)


@router.get("/processes/{process_id}/voice-notes")
async def list_voice_notes(process_id: str, user: dict = Depends(get_current_user)):
    """Lista as notas de voz registadas no processo."""
    return await run_list_voice_notes(process_id, user)
