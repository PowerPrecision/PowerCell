"""User ↔ S3 folder mapping ops.

Do NOT name this module `admin_storage.py` (collides with routes/admin_storage.py).
Extraído de `routes/admin_storage.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.s3_document_root import (
    PastaGravadaInvalida,
    pasta_para_gravar,
)

logger = logging.getLogger(__name__)


async def run_get_user_s3_mappings(user: dict):
    """Lista mapeamentos de utilizadores para pastas S3."""
    users = await db.users.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "s3_folder": 1, "role": 1}
    ).to_list(500)

    from services.s3_storage import s3_service
    available_folders = []

    if s3_service.is_configured():
        try:
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket_name,
                Prefix="Documentação Clientes/",
                Delimiter="/"
            )

            for prefix in response.get("CommonPrefixes", []):
                folder_path = prefix.get("Prefix", "")
                folder_name = folder_path.replace("Documentação Clientes/", "").rstrip("/")
                if folder_name:
                    available_folders.append({
                        "path": folder_path.rstrip("/"),
                        "name": folder_name
                    })
        except Exception as e:
            logger.warning(f"Erro ao listar pastas S3: {e}")

    return {
        "users": users,
        "available_folders": available_folders,
        "s3_configured": s3_service.is_configured()
    }


async def run_update_user_s3_mapping(user_id: str, s3_folder: str | None, user: dict):
    """Actualiza o mapeamento de um utilizador para uma pasta S3.

    LOTE 9 — este escritor não tinha validação NENHUMA. O irmão do lado
    (`admin_s3_process_mappings`) ganhou o `_clean_s3_folder` no Lote 8 e
    este ficou de fora: a anotação `str | None` é documentação, não uma
    parede, e o valor entrava tal e qual na base de dados. É a forma do
    defeito do Lote 5 (o `set` e o `clear` a divergirem) aplicada a dois
    endpoints irmãos que gravam o MESMO campo.
    """
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    try:
        caminho = pasta_para_gravar(
            s3_folder, contexto=f"mapeamento do utilizador {user_id}"
        )
    except PastaGravadaInvalida as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    update_data = {
        "s3_folder": caminho,
        "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
        "s3_mapping_updated_by": user["id"]
    }

    await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )

    await db.activity_logs.insert_one({
        "type": "user_s3_mapping_updated",
        "user_id": user_id,
        "updated_by": user["id"],
        "s3_folder": caminho,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {"success": True, "user_id": user_id, "s3_folder": caminho}


async def run_get_user_s3_mapping(user_id: str, user: dict):
    """Obtém mapeamento S3 de um utilizador específico."""
    target_user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "s3_folder": 1, "role": 1}
    )

    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    return target_user
