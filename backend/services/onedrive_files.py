"""List client files by name (S3) for OneDrive routes.

Extraído de `routes/onedrive.py`.
Do **not** overwrite `services/onedrive.py`.
"""
from __future__ import annotations

from database import db


async def run_get_client_files_by_name(
    client_name: str,
    subfolder: str,
    user: dict,
):
    """
    Listar ficheiros de um cliente pelo nome.
    Redireciona para o serviço S3 de documentos.
    """
    from services.s3_storage import s3_service

    process = await db.processes.find_one(
        {"client_name": {"$regex": f"^{client_name}$", "$options": "i"}},
        {
            "_id": 0,
            "id": 1,
            "client_name": 1,
            "second_client_name": 1,
            "titular2_data": 1,
        },
    )

    if not process:
        process = await db.processes.find_one(
            {"client_name": {"$regex": client_name, "$options": "i"}},
            {
                "_id": 0,
                "id": 1,
                "client_name": 1,
                "second_client_name": 1,
                "titular2_data": 1,
            },
        )

    if not process:
        return {
            "files": [],
            "folders": [],
            "message": f"Cliente '{client_name}' não encontrado",
        }

    client_id = process.get("id")
    real_client_name = process.get("client_name", client_name)
    second_client_name = process.get("second_client_name") or \
        process.get("titular2_data", {}).get("nome")

    return s3_service.list_files(client_id, real_client_name, second_client_name)
