"""Client S3 mapping ops (auto-map) — aliases live in the route stubs.

Do NOT name this module `admin_storage.py` (collides with routes/admin_storage.py).
Extraído de `routes/admin_storage.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)


async def run_auto_map_client_s3_folders(user: dict):
    """
    Mapeamento automático de pastas S3 para processos baseado em nome.

    Se o processo não tiver client_name, o nome da pasta é usado para preencher.
    """
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    results = {"mapped": 0, "skipped": 0, "updated_names": 0, "errors": []}

    try:
        # Listar pastas S3
        response = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name,
            Prefix="Documentação Clientes/",
            Delimiter="/"
        )

        folders = []
        for prefix in response.get("CommonPrefixes", []):
            folder_path = prefix.get("Prefix", "").rstrip("/")
            folder_name = folder_path.replace("Documentação Clientes/", "")
            if folder_name:
                folders.append({"path": folder_path, "name": folder_name})

        # Para cada pasta, tentar encontrar processo correspondente
        for folder in folders:
            folder_name = folder["name"]

            # Tentar converter nome da pasta para formato legível (underscores -> espaços)
            folder_name_readable = folder_name.replace("_", " ").replace("  ", " ")

            # Procurar processo pelo nome do cliente (exact match case-insensitive)
            process = await db.processes.find_one(
                {"client_name": {"$regex": f"^{folder_name}$", "$options": "i"}},
                {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}
            )

            # Se não encontrou, tentar com nome legível
            if not process:
                process = await db.processes.find_one(
                    {"client_name": {"$regex": f"^{folder_name_readable}$", "$options": "i"}},
                    {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}
                )

            # Se ainda não encontrou, tentar match parcial
            if not process:
                # Procurar por processos que contenham o nome da pasta ou vice-versa
                name_parts = folder_name.replace("_", " ").split()
                if len(name_parts) >= 2:
                    # Usar primeiros nomes para match mais flexível
                    first_name = name_parts[0]
                    last_name = name_parts[-1]
                    process = await db.processes.find_one(
                        {"client_name": {"$regex": f"{first_name}.*{last_name}", "$options": "i"}},
                        {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}
                    )

            if process:
                update_fields = {"s3_folder": folder["path"]}

                # Se o processo não tem client_name, usar o nome da pasta
                if not process.get("client_name") or process.get("client_name") == "Sem nome":
                    update_fields["client_name"] = folder_name_readable
                    results["updated_names"] += 1

                if not process.get("s3_folder"):
                    await db.processes.update_one(
                        {"id": process["id"]},
                        {"$set": update_fields}
                    )
                    results["mapped"] += 1
                else:
                    results["skipped"] += 1
            else:
                results["skipped"] += 1

    except Exception as e:
        results["errors"].append(str(e))

    return results
