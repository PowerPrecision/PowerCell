"""Process folder URL get/save/delete for OneDrive routes.

Extraído de `routes/onedrive.py`.
Do **not** overwrite `services/onedrive.py`.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from database import db
from services.onedrive_url_validation import is_valid_folder_url

ONEDRIVE_SHARED_LINK = os.environ.get("ONEDRIVE_SHARED_LINK", "")
ONEDRIVE_WEB_URL = os.environ.get("ONEDRIVE_WEB_URL", "")


async def run_get_process_folder_url(process_id: str, user: dict):
    """Obter URL para abrir a pasta do cliente no OneDrive."""
    if not ONEDRIVE_SHARED_LINK:
        raise HTTPException(status_code=400, detail="OneDrive não configurado")

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client_name = process.get("client_name", "")
    saved_folder_url = process.get("onedrive_folder_url")

    if saved_folder_url:
        return {
            "url": saved_folder_url,
            "client_name": client_name,
            "type": "saved",
            "message": "Link guardado no processo",
        }

    return {
        "url": ONEDRIVE_SHARED_LINK,
        "web_url": ONEDRIVE_WEB_URL,
        "client_name": client_name,
        "type": "main_folder",
        "message": f"Abrir pasta principal e procurar por '{client_name}'",
    }


async def run_save_process_folder_url(process_id: str, folder_url: str, user: dict):
    """Guardar o link da pasta do cliente no processo."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if not is_valid_folder_url(folder_url):
        raise HTTPException(
            status_code=400,
            detail=(
                "URL inválido. Use um link de Drive, OneDrive, Google Drive, "
                "S3 ou outro serviço de cloud."
            ),
        )

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"onedrive_folder_url": folder_url, "cloud_folder_url": folder_url}},
    )

    return {
        "success": True,
        "message": "Link da pasta guardado com sucesso",
    }


async def run_remove_process_folder_url(process_id: str, user: dict):
    """Remover o link da pasta do processo."""
    result = await db.processes.update_one(
        {"id": process_id},
        {"$unset": {"onedrive_folder_url": ""}},
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado ou link já removido",
        )

    return {"success": True, "message": "Link removido"}
