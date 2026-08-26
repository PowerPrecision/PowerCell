"""Process ↔ S3 folder mapping ops (list/update/fix-missing/batch).

Do NOT name this module `admin_storage.py` (collides with routes/admin_storage.py).
Extraído de `routes/admin_storage.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException

from database import db
from services.process_status import ARCHIVED_STATUSES, DELETED_STATUS_VALUES

logger = logging.getLogger(__name__)


def _clean_s3_folder(s3_folder: Optional[str]) -> Optional[str]:
    """Validar s3_folder — não guardar "undefined", "null" ou strings inválidas."""
    if s3_folder in [None, "", "undefined", "null", "None"]:
        return None
    return s3_folder


async def run_get_process_s3_mappings(
    search: Optional[str],
    status: Optional[str],
    has_mapping: Optional[bool],
    include_closed: bool,
    include_deleted: bool,
    page: int,
    limit: int,
    user: dict,
):
    """Lista mapeamentos de processos para pastas S3."""
    query = {}

    # Por defeito, excluir processos concluídos e desistências
    # Fix: Normalize process status filters — inclui as variações legadas
    # singular/plural (ver services/process_status.py).
    if not include_closed:
        query["status"] = {"$nin": list(ARCHIVED_STATUSES)}

    # Por defeito, excluir processos eliminados (soft delete)
    if not include_deleted:
        query["is_active"] = {"$ne": False}
        # Também excluir por status "eliminado"/"eliminados" para compatibilidade
        if "status" in query:
            query["status"]["$nin"] = list(
                set(query["status"].get("$nin", [])) | set(DELETED_STATUS_VALUES)
            )
        else:
            query["status"] = {"$nin": list(DELETED_STATUS_VALUES)}

    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_email": {"$regex": search, "$options": "i"}},
            {"process_number": {"$regex": search, "$options": "i"}}
        ]

    if status:
        query["status"] = status

    if has_mapping is not None:
        if has_mapping:
            query["s3_folder"] = {"$exists": True, "$nin": [None, ""]}
        else:
            query["$or"] = [
                {"s3_folder": {"$exists": False}},
                {"s3_folder": None},
                {"s3_folder": ""}
            ]

    skip = (page - 1) * limit

    total = await db.processes.count_documents(query)

    # Contar processos com e sem mapeamento S3
    mapped_count = await db.processes.count_documents({
        **query,
        "s3_folder": {"$exists": True, "$ne": None, "$ne": ""}
    })
    unmapped_count = total - mapped_count

    processes = await db.processes.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "process_number": 1,
            "client_name": 1,
            "client_email": 1,
            "status": 1,
            "s3_folder": 1,
            "created_at": 1
        }
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

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
        "processes": processes,
        "available_folders": available_folders,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "s3_configured": s3_service.is_configured(),
        "stats": {
            "total": total,
            "mapped": mapped_count,
            "unmapped": unmapped_count
        }
    }


async def run_update_process_s3_mapping(process_id: str, s3_folder: Optional[str], user: dict):
    """Actualiza o mapeamento de um processo para uma pasta S3."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    clean_s3_folder = _clean_s3_folder(s3_folder)

    update_data = {
        "s3_folder": clean_s3_folder,
        "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
        "s3_mapping_updated_by": user["id"]
    }

    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )

    await db.activity_logs.insert_one({
        "type": "process_s3_mapping_updated",
        "process_id": process_id,
        "updated_by": user["id"],
        "s3_folder": clean_s3_folder,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {
        "success": True,
        "process_id": process_id,
        "s3_folder": clean_s3_folder,
        "client_name": process.get("client_name"),
    }


async def run_fix_missing_client_names(user: dict):
    """
    Corrige processos que não têm client_name definido.
    Extrai o nome da pasta S3 mapeada ou do email do cliente.
    """
    fixed_count = 0

    # Processos sem nome ou com nome "Sem nome"
    processes_without_name = await db.processes.find({
        "$or": [
            {"client_name": None},
            {"client_name": ""},
            {"client_name": "Sem nome"},
            {"client_name": {"$exists": False}}
        ]
    }).to_list(1000)

    for process in processes_without_name:
        new_name = None

        # 1. Tentar extrair da pasta S3
        s3_folder = process.get("s3_folder")
        if s3_folder:
            # Extrair nome da pasta: "Documentação Clientes/Nome_Cliente" -> "Nome Cliente"
            folder_name = s3_folder.replace("Documentação Clientes/", "").rstrip("/")
            if folder_name:
                new_name = folder_name.replace("_", " ").replace("  ", " ")

        # 2. Tentar extrair do email
        if not new_name:
            email = process.get("client_email")
            if email and "@" in email:
                email_name = email.split("@")[0]
                new_name = email_name.replace(".", " ").replace("_", " ").replace("-", " ").title()

        # 3. Tentar extrair de personal_data
        if not new_name:
            personal = process.get("personal_data", {})
            new_name = (
                personal.get("nome_completo") or
                personal.get("nome") or
                personal.get("name")
            )

        # 4. Se ainda não temos nome, usar "Cliente" com número do processo
        if not new_name:
            process_num = process.get("process_number", "Desconhecido")
            new_name = f"Cliente #{process_num}"

        # Actualizar o processo
        if new_name:
            await db.processes.update_one(
                {"id": process["id"]},
                {"$set": {"client_name": new_name, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            fixed_count += 1

    return {
        "success": True,
        "message": f"Corrigidos {fixed_count} processos sem nome",
        "fixed_count": fixed_count,
        "total_found": len(processes_without_name)
    }


async def run_batch_update_process_s3_mappings(mappings: List[dict], user: dict):
    """Actualiza mapeamentos S3 em batch para múltiplos processos."""
    results = {"updated": 0, "failed": 0, "errors": []}

    for mapping in mappings:
        process_id = mapping.get("process_id")
        s3_folder = mapping.get("s3_folder")

        if not process_id:
            results["failed"] += 1
            results["errors"].append({"error": "process_id é obrigatório"})
            continue

        try:
            process = await db.processes.find_one({"id": process_id})
            if not process:
                results["failed"] += 1
                results["errors"].append({"process_id": process_id, "error": "Processo não encontrado"})
                continue

            clean_s3_folder = _clean_s3_folder(s3_folder)

            update_data = {
                "s3_folder": clean_s3_folder,
                "s3_mapping_updated_at": datetime.now(timezone.utc).isoformat(),
                "s3_mapping_updated_by": user["id"]
            }

            await db.processes.update_one(
                {"id": process_id},
                {"$set": update_data}
            )

            results["updated"] += 1

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"process_id": process_id, "error": str(e)})

    # Retornar formato esperado pelo frontend
    return {
        "success": results["failed"] == 0 or results["updated"] > 0,
        "updated": results["updated"],
        "failed": results["failed"],
        "errors": results["errors"]
    }
