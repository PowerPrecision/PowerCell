"""Storage process folder-url handlers.

Extraído de `routes/storage.py`.
Do **not** overwrite s3_storage.py / storage_service.py — use storage_api_*.
"""
from __future__ import annotations

from fastapi import HTTPException

from database import db


async def run_get_process_folder_url(process_id: str):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    client_name = process.get("client_name", "")
    saved_folder_url = (
        process.get("storage_folder_url")
        or process.get("onedrive_folder_url")
        or process.get("drive_folder_url")
    )

    if saved_folder_url:
        return {
            "url": saved_folder_url,
            "client_name": client_name,
            "type": "saved",
            "message": "Link guardado no processo"
        }

    return {
        "url": None,
        "client_name": client_name,
        "type": "none",
        "message": "Nenhum link de pasta configurado para este processo"
    }


async def run_save_process_folder_url(process_id: str, folder_url: str):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if not folder_url or len(folder_url) < 5:
        raise HTTPException(status_code=400, detail="URL inválido")

    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"storage_folder_url": folder_url}}
    )

    return {
        "success": True,
        "message": "Link da pasta guardado com sucesso",
        "url": folder_url
    }


async def run_delete_process_folder_url(process_id: str):
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    await db.processes.update_one(
        {"id": process_id},
        {"$unset": {
            "storage_folder_url": "",
            "onedrive_folder_url": "",
            "drive_folder_url": ""
        }}
    )

    return {
        "success": True,
        "message": "Link da pasta removido"
    }
