"""TTL migration and status diagnostics.

Extraído de `routes/diagnostics.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from database import db
from services.diagnostics_helpers import TTLMigrationResult, TTLMigrationResponse

logger = logging.getLogger(__name__)


async def run_migrate_ttl_datetime_fields() -> TTLMigrationResponse:
    """
    Migra documentos existentes para incluir campos datetime nativos (*_dt).

    Os índices TTL do MongoDB requerem campos BSON Date (datetime nativo).
    Documentos antigos têm apenas campos ISO string, que NÃO funcionam com TTL.

    Este endpoint popula os campos:
    - refresh_tokens: created_at_dt
    - system_error_logs: timestamp_dt
    - emails (drafts): updated_at_dt

    Após a migração, os índices TTL começarão a purgar documentos antigos.
    """
    results = []
    total_migrated = 0

    # ====================================================================
    # 1. MIGRAR REFRESH_TOKENS
    # ====================================================================
    try:
        # Contar documentos sem campo created_at_dt
        total = await db.refresh_tokens.count_documents({})
        without_dt = await db.refresh_tokens.count_documents({"created_at_dt": {"$exists": False}})

        migrated = 0
        errors = 0
        details = []

        if without_dt > 0:
            # Buscar documentos que precisam de migração
            cursor = db.refresh_tokens.find({
                "created_at_dt": {"$exists": False},
                "created_at": {"$exists": True}
            })

            async for doc in cursor:
                try:
                    # Converter ISO string para datetime
                    created_at_str = doc.get("created_at")
                    if created_at_str:
                        created_at_dt = datetime.fromisoformat(
                            created_at_str.replace("Z", "+00:00")
                        )

                        await db.refresh_tokens.update_one(
                            {"id": doc["id"]},
                            {"$set": {"created_at_dt": created_at_dt}}
                        )
                        migrated += 1
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        details.append(f"Erro em refresh_token {doc.get('id')}: {str(e)}")

        results.append(TTLMigrationResult(
            collection="refresh_tokens",
            total_documents=total,
            migrated=migrated,
            already_migrated=total - without_dt,
            errors=errors,
            details=details
        ))
        total_migrated += migrated

    except Exception as e:
        logger.error(f"Erro ao migrar refresh_tokens: {e}")
        results.append(TTLMigrationResult(
            collection="refresh_tokens",
            total_documents=0,
            migrated=0,
            already_migrated=0,
            errors=1,
            details=[f"Erro geral: {str(e)}"]
        ))

    # ====================================================================
    # 2. MIGRAR SYSTEM_ERROR_LOGS
    # ====================================================================
    try:
        total = await db.system_error_logs.count_documents({})
        without_dt = await db.system_error_logs.count_documents({"timestamp_dt": {"$exists": False}})

        migrated = 0
        errors = 0
        details = []

        if without_dt > 0:
            cursor = db.system_error_logs.find({
                "timestamp_dt": {"$exists": False},
                "timestamp": {"$exists": True}
            })

            async for doc in cursor:
                try:
                    timestamp_str = doc.get("timestamp")
                    if timestamp_str:
                        timestamp_dt = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                        )

                        await db.system_error_logs.update_one(
                            {"id": doc["id"]},
                            {"$set": {"timestamp_dt": timestamp_dt}}
                        )
                        migrated += 1
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        details.append(f"Erro em system_error_log {doc.get('id')}: {str(e)}")

        results.append(TTLMigrationResult(
            collection="system_error_logs",
            total_documents=total,
            migrated=migrated,
            already_migrated=total - without_dt,
            errors=errors,
            details=details
        ))
        total_migrated += migrated

    except Exception as e:
        logger.error(f"Erro ao migrar system_error_logs: {e}")
        results.append(TTLMigrationResult(
            collection="system_error_logs",
            total_documents=0,
            migrated=0,
            already_migrated=0,
            errors=1,
            details=[f"Erro geral: {str(e)}"]
        ))

    # ====================================================================
    # 3. MIGRAR EMAILS (DRAFTS)
    # ====================================================================
    try:
        # Apenas rascunhos são elegíveis para TTL
        total = await db.emails.count_documents({"status": "draft"})
        without_dt = await db.emails.count_documents({
            "status": "draft",
            "updated_at_dt": {"$exists": False}
        })

        migrated = 0
        errors = 0
        details = []

        if without_dt > 0:
            cursor = db.emails.find({
                "status": "draft",
                "updated_at_dt": {"$exists": False},
                "updated_at": {"$exists": True}
            })

            async for doc in cursor:
                try:
                    updated_at_str = doc.get("updated_at")
                    if updated_at_str:
                        updated_at_dt = datetime.fromisoformat(
                            updated_at_str.replace("Z", "+00:00")
                        )

                        # Também criar created_at_dt se não existir
                        created_at_dt = None
                        created_at_str = doc.get("created_at")
                        if created_at_str:
                            created_at_dt = datetime.fromisoformat(
                                created_at_str.replace("Z", "+00:00")
                            )

                        update_fields = {"updated_at_dt": updated_at_dt}
                        if created_at_dt:
                            update_fields["created_at_dt"] = created_at_dt

                        await db.emails.update_one(
                            {"id": doc["id"]},
                            {"$set": update_fields}
                        )
                        migrated += 1
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        details.append(f"Erro em email {doc.get('id')}: {str(e)}")

        results.append(TTLMigrationResult(
            collection="emails (drafts)",
            total_documents=total,
            migrated=migrated,
            already_migrated=total - without_dt,
            errors=errors,
            details=details
        ))
        total_migrated += migrated

    except Exception as e:
        logger.error(f"Erro ao migrar emails: {e}")
        results.append(TTLMigrationResult(
            collection="emails (drafts)",
            total_documents=0,
            migrated=0,
            already_migrated=0,
            errors=1,
            details=[f"Erro geral: {str(e)}"]
        ))

    # Mensagem de resumo
    if total_migrated > 0:
        message = f"✅ Migração concluída: {total_migrated} documentos migrados. Os índices TTL começarão a purgar documentos antigos automaticamente."
    else:
        message = "ℹ️ Todos os documentos já têm campos datetime. Nenhuma migração necessária."

    logger.info(f"Migração TTL: {total_migrated} documentos migrados")

    return TTLMigrationResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        results=results,
        total_migrated=total_migrated,
        message=message
    )


async def run_get_ttl_index_status():
    """
    Retorna o estado dos índices TTL e contagem de documentos migrados/pendentes.
    """
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "collections": []
    }

    # Verificar cada coleção com TTL
    ttl_collections = [
        {
            "name": "refresh_tokens",
            "ttl_field": "created_at_dt",
            "ttl_seconds": 86400,
            "ttl_description": "24 horas"
        },
        {
            "name": "system_error_logs",
            "ttl_field": "timestamp_dt",
            "ttl_seconds": 2592000,
            "ttl_description": "30 dias"
        },
        {
            "name": "emails",
            "ttl_field": "updated_at_dt",
            "ttl_seconds": 604800,
            "ttl_description": "7 dias (rascunhos)",
            "filter": {"status": "draft"}
        }
    ]

    for col in ttl_collections:
        try:
            collection = db[col["name"]]

            # Contar total
            if col.get("filter"):
                total = await collection.count_documents(col["filter"])
            else:
                total = await collection.count_documents({})

            # Contar com campo datetime
            query = {col["ttl_field"]: {"$exists": True}}
            if col.get("filter"):
                query.update(col["filter"])

            with_dt = await collection.count_documents(query)

            # Verificar se índice TTL existe
            indexes = await collection.index_information()
            ttl_index_exists = any(
                idx.get("expireAfterSeconds") == col["ttl_seconds"]
                for idx in indexes.values()
            )

            status["collections"].append({
                "name": col["name"],
                "ttl_field": col["ttl_field"],
                "ttl_seconds": col["ttl_seconds"],
                "ttl_description": col["ttl_description"],
                "total_documents": total,
                "with_datetime_field": with_dt,
                "pending_migration": total - with_dt,
                "ttl_index_exists": ttl_index_exists,
                "status": "ok" if with_dt == total and ttl_index_exists else "needs_migration" if with_dt < total else "no_index"
            })

        except Exception as e:
            status["collections"].append({
                "name": col["name"],
                "error": str(e),
                "status": "error"
            })

    return status
