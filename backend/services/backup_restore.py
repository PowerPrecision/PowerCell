"""Backup restore — restore-from-s3 + emergency atomic-swap restore.

Extracted from `routes/backup.py`. Reuses `services.backup.get_s3_client`.
Does **not** overwrite `services/backup.py`.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

from bson import json_util
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from config import DB_NAME, MONGO_URL
from services.backup import get_s3_client

logger = logging.getLogger(__name__)

# Coleções a ignorar no restore de emergência (metadata interna / config actual)
RESTORE_IGNORE_COLLECTIONS = {
    "backup_history",
    "system.indexes",
    "system_config",  # Preservar config atual do sistema
}

# Coleções principais onde recriar índices únicos após o swap
RESTORE_INDEX_COLLECTIONS = [
    "users", "clients", "processes", "documents", "tasks", "history",
    "activities", "properties", "announcements", "portal_messages",
    "workflow_statuses", "companies", "user_company_roles",
    "user_email_configs", "refresh_tokens", "deadlines",
]

# Índices por coleção (chave, nome, unique?)
_INDEX_DEFINITIONS = {
    "users": [
        {"keys": [("email", 1)], "name": "idx_email", "unique": True},
        {"keys": [("id", 1)], "name": "idx_user_id", "unique": True},
    ],
    "clients": [
        {"keys": [("id", 1)], "name": "idx_client_id", "unique": True},
        {"keys": [("contacto.email_hash", 1)], "name": "idx_client_email_hash", "sparse": True},
    ],
    "processes": [
        {"keys": [("id", 1)], "name": "idx_process_id", "unique": True},
        {"keys": [("client_id", 1)], "name": "idx_process_client_id"},
        {"keys": [("status", 1)], "name": "idx_process_status"},
    ],
    "documents": [
        {"keys": [("id", 1)], "name": "idx_doc_id", "unique": True},
        {"keys": [("process_id", 1)], "name": "idx_doc_process_id"},
    ],
    "tasks": [
        {"keys": [("id", 1)], "name": "idx_task_id", "unique": True},
        {"keys": [("process_id", 1)], "name": "idx_task_process_id"},
    ],
    "history": [
        {"keys": [("process_id", 1), ("created_at", -1)], "name": "idx_history_process_date"},
    ],
    "activities": [
        {"keys": [("process_id", 1), ("created_at", -1)], "name": "idx_activity_process_date"},
    ],
    "properties": [
        {"keys": [("id", 1)], "name": "idx_property_id", "unique": True},
    ],
    "announcements": [
        {"keys": [("id", 1)], "name": "idx_announcement_id", "unique": True},
    ],
    "portal_messages": [
        {"keys": [("process_id", 1)], "name": "idx_portal_msg_process"},
    ],
    "workflow_statuses": [
        {"keys": [("name", 1)], "name": "idx_workflow_name", "unique": True},
    ],
    "companies": [
        {"keys": [("id", 1)], "name": "idx_company_id", "unique": True},
    ],
    "user_company_roles": [
        {
            "keys": [("user_id", 1), ("company_id", 1), ("role", 1)],
            "name": "idx_user_company_role_unique",
            "unique": True,
        },
    ],
    "user_email_configs": [
        {"keys": [("user_id", 1), ("company_id", 1)], "name": "idx_uec_unique", "unique": True},
    ],
    "refresh_tokens": [
        {"keys": [("token_hash", 1)], "name": "idx_token_hash", "unique": True},
    ],
    "deadlines": [
        {"keys": [("id", 1)], "name": "idx_deadline_id", "unique": True},
    ],
}


def _require_restore_confirm(data: dict, *, atomic: bool = False) -> None:
    confirm = data.get("confirm")
    if confirm != "RESTAURAR_PRODUCAO":
        detail = (
            'Para confirmar, envie {"confirm": "RESTAURAR_PRODUCAO"} no body. '
            "Esta operação sobrescreve TODOS os dados da BD"
            + (" com swap atómico." if atomic else ".")
        )
        raise HTTPException(status_code=400, detail=detail)


def _list_s3_backup_keys(
    s3_client,
    bucket_name: str,
    backup_key: str | None,
    *,
    empty_detail: str = "Nenhum backup encontrado no S3",
) -> list[str]:
    if backup_key:
        return [backup_key]

    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Prefix="backups/",
    )
    s3_keys = sorted(
        [
            obj["Key"]
            for obj in response.get("Contents", [])
            if obj["Key"].endswith(".zip")
        ],
        reverse=True,
    )
    if not s3_keys:
        raise HTTPException(status_code=404, detail=empty_detail)
    return s3_keys


async def run_restore_from_s3(data: dict, user: dict) -> dict:
    """
    Restaura a base de dados de Produção a partir do backup mais recente no S3.
    ATENÇÃO: Este endpoint sobrescreve TODOS os dados da BD actual.
    """
    _require_restore_confirm(data, atomic=False)

    backup_key = data.get("backup_key")
    collections_to_restore = data.get("collections")

    logger.warning(f"[RESTORE] Restore de Produção iniciado por {user.get('email')}")

    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(
            status_code=500,
            detail="S3 não configurado — credenciais AWS em falta",
        )

    bucket_name = os.environ.get("AWS_BUCKET_NAME", "")
    tmp_dir = tempfile.mkdtemp()
    stats = {"collections": {}, "total_documents": 0, "errors": [], "warnings": []}

    try:
        s3_keys = _list_s3_backup_keys(s3_client, bucket_name, backup_key)
        selected_key = s3_keys[0]
        logger.info(f"[RESTORE] A usar backup: {selected_key}")

        zip_buffer = io.BytesIO()
        s3_client.download_fileobj(bucket_name, selected_key, zip_buffer)
        zip_buffer.seek(0)

        client = AsyncIOMotorClient(MONGO_URL)
        database = client[DB_NAME]

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            json_files = [f for f in zf.namelist() if f.endswith(".json")]

            for json_file in json_files:
                col_name = json_file.replace(".json", "").split("/")[-1]

                if collections_to_restore and col_name not in collections_to_restore:
                    continue

                try:
                    content = zf.read(json_file)
                    docs = json_util.loads(content)

                    if not isinstance(docs, list) or not docs:
                        stats["warnings"].append(
                            f"Colecção {col_name}: sem documentos válidos"
                        )
                        continue

                    await database[col_name].delete_many({})
                    if docs:
                        await database[col_name].insert_many(docs)
                        stats["collections"][col_name] = len(docs)
                        stats["total_documents"] += len(docs)

                    logger.info(
                        f"[RESTORE] {col_name}: {len(docs)} documentos restaurados"
                    )

                except Exception as e:
                    stats["errors"].append(f"{col_name}: {str(e)}")
                    logger.error(f"[RESTORE] Erro em {col_name}: {e}")

        client.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

        logger.info(
            f"[RESTORE] Concluído: {stats['total_documents']} documentos em "
            f"{len(stats['collections'])} colecções"
        )

        return {
            "success": len(stats["errors"]) == 0,
            "backup_key": selected_key,
            "collections": stats["collections"],
            "total_documents": stats["total_documents"],
            "errors": stats["errors"],
            "warnings": stats["warnings"],
            "restored_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[RESTORE] Erro fatal: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Erro no restore: {str(e)}")


async def run_emergency_restore(data: dict, user: dict) -> dict:
    """
    PACOTE CD — Restauro de emergência com swap atómico.

    Restaura a BD de Produção a partir do backup mais recente no S3,
    usando coleções temporárias e rename atómico para garantir que a BD
    nunca fica inconsistente (mesmo que o processo falhe a meio).
    """
    _require_restore_confirm(data, atomic=True)

    backup_key = data.get("backup_key")
    collections_to_restore = data.get("collections")

    logger.warning(
        f"[RESTORE-CD] Restauro de emergência (swap atómico) iniciado por "
        f"{user.get('email')} — backup_key={backup_key or 'mais recente'}"
    )

    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(
            status_code=500,
            detail="S3 não configurado — credenciais AWS em falta. "
                   "Configure AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY e AWS_BUCKET_NAME.",
        )

    bucket_name = os.environ.get("AWS_BUCKET_NAME", "")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="AWS_BUCKET_NAME não configurado")

    stats = {
        "collections": {},
        "total_documents": 0,
        "errors": [],
        "warnings": [],
        "swapped": [],
        "temp_prefix": "_restore_",
    }

    try:
        # 1. ENCONTRAR E DOWNLOAD DO BACKUP NO S3
        s3_keys = _list_s3_backup_keys(
            s3_client,
            bucket_name,
            backup_key,
            empty_detail="Nenhum backup encontrado no S3 (prefixo backups/)",
        )
        selected_key = s3_keys[0]
        logger.info(f"[RESTORE-CD] A usar backup: {selected_key}")

        zip_buffer = io.BytesIO()
        s3_client.download_fileobj(bucket_name, selected_key, zip_buffer)
        zip_buffer.seek(0)

        # 2. EXTRAIR JSON DAS COLEÇÕES DO ZIP
        extracted_data = {}

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            json_files = [f for f in zf.namelist() if f.endswith(".json")]

            for json_file in json_files:
                col_name = json_file.replace(".json", "").split("/")[-1]

                if col_name in RESTORE_IGNORE_COLLECTIONS:
                    stats["warnings"].append(f"Ignorada: {col_name}")
                    continue

                if collections_to_restore and col_name not in collections_to_restore:
                    continue

                try:
                    content = zf.read(json_file)
                    docs = json_util.loads(content)

                    if not isinstance(docs, list) or not docs:
                        stats["warnings"].append(f"{col_name}: sem documentos válidos")
                        continue

                    extracted_data[col_name] = docs
                    logger.info(
                        f"[RESTORE-CD] Extraído: {col_name} ({len(docs)} docs)"
                    )

                except Exception as e:
                    stats["errors"].append(f"Extrair {col_name}: {str(e)}")
                    logger.error(f"[RESTORE-CD] Erro ao extrair {col_name}: {e}")

        if not extracted_data:
            raise HTTPException(
                status_code=500,
                detail="Nenhuma coleção válida encontrada no ZIP de backup",
            )

        # 3. INSERT_MANY PARA COLEÇÕES TEMPORÁRIAS (_restore_*)
        client = AsyncIOMotorClient(MONGO_URL)
        database = client[DB_NAME]
        temp_prefix = stats["temp_prefix"]

        for col_name, docs in extracted_data.items():
            temp_col = f"{temp_prefix}{col_name}"
            try:
                await database[temp_col].drop()
                await database[temp_col].insert_many(docs)
                stats["collections"][col_name] = len(docs)
                stats["total_documents"] += len(docs)
                logger.info(
                    f"[RESTORE-CD] Temporária {temp_col}: {len(docs)} docs inseridos"
                )
            except Exception as e:
                stats["errors"].append(f"Insert {temp_col}: {str(e)}")
                logger.error(f"[RESTORE-CD] Erro ao inserir em {temp_col}: {e}")

        if len(stats["errors"]) == len(extracted_data):
            for col_name in extracted_data:
                await database[f"{temp_prefix}{col_name}"].drop()
            client.close()
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Todos os inserts falharam. Swap abortado. "
                    f"Erros: {stats['errors'][:3]}"
                ),
            )

        # 4. SWAP ATÓMICO: drop() real + rename() temporária
        for col_name in extracted_data:
            temp_col = f"{temp_prefix}{col_name}"
            if col_name not in stats["collections"]:
                continue

            try:
                temp_count = await database[temp_col].count_documents({})
                if temp_count == 0:
                    stats["warnings"].append(f"Swap {col_name}: temporária vazia, skip")
                    await database[temp_col].drop()
                    continue

                await database[col_name].drop()
                await database[temp_col].rename(col_name)
                stats["swapped"].append(col_name)
                logger.info(
                    f"[RESTORE-CD] Swap atómico: {temp_col} → {col_name} "
                    f"({temp_count} docs)"
                )

            except Exception as e:
                stats["errors"].append(f"Swap {col_name}: {str(e)}")
                logger.error(f"[RESTORE-CD] Erro no swap de {col_name}: {e}")
                try:
                    await database[temp_col].drop()
                except Exception:
                    pass

        # 5. RECRIAR ÍNDICES NAS COLEÇÕES PRINCIPAIS
        index_stats = {"created": 0, "errors": []}

        for col_name, index_defs in _INDEX_DEFINITIONS.items():
            if col_name not in stats["swapped"]:
                continue
            collection = database[col_name]
            for idx_def in index_defs:
                try:
                    keys = idx_def["keys"]
                    kwargs = {"name": idx_def["name"]}
                    if idx_def.get("unique"):
                        kwargs["unique"] = True
                    if idx_def.get("sparse"):
                        kwargs["sparse"] = True
                    await collection.create_index(keys, **kwargs)
                    index_stats["created"] += 1
                except Exception as e:
                    idx_name = idx_def.get("name", "unknown")
                    index_stats["errors"].append(f"{col_name}.{idx_name}: {str(e)}")
                    logger.warning(f"[RESTORE-CD] Índice {col_name}.{idx_name}: {e}")

        # 6. LIMPEZA DE TEMPORÁRIAS ÓRFÃS
        for col_name in extracted_data:
            temp_col = f"{temp_prefix}{col_name}"
            try:
                cols = await database.list_collection_names()
                if temp_col in cols:
                    await database[temp_col].drop()
                    logger.info(
                        f"[RESTORE-CD] Limpeza: temporária órfã {temp_col} removida"
                    )
            except Exception:
                pass

        client.close()

        logger.info(
            f"[RESTORE-CD] Concluído: {stats['total_documents']} documentos em "
            f"{len(stats['swapped'])} coleções swapped, "
            f"{index_stats['created']} índices criados. "
            f"Erros: {len(stats['errors'])}, Avisos: {len(stats['warnings'])}"
        )

        return {
            "success": len(stats["errors"]) == 0,
            "backup_key": selected_key,
            "method": "atomic_swap",
            "collections_restored": stats["collections"],
            "collections_swapped": stats["swapped"],
            "total_documents": stats["total_documents"],
            "indexes_created": index_stats["created"],
            "index_errors": index_stats["errors"],
            "errors": stats["errors"],
            "warnings": stats["warnings"],
            "ignored": list(RESTORE_IGNORE_COLLECTIONS),
            "restored_by": user.get("email"),
            "restored_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[RESTORE-CD] Erro fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro no restore de emergência: {str(e)}",
        )
