"""Background bulk RGPD encryption migration task.

Extraído de `routes/admin_migration.py`.
"""
from __future__ import annotations

import logging

from database import db
from services.admin_migration_api_helpers import build_client_encryption_updates
from services.system_error_logger import system_error_logger

logger = logging.getLogger(__name__)


async def run_migration_task():
    """Tarefa em background para executar a migração RGPD de clientes."""
    logger.info("=" * 60)
    logger.info("INICIANDO MIGRAÇÃO RGPD DE CLIENTES")
    logger.info("=" * 60)

    try:
        cursor = db.clients.find({}, {
            "_id": 1, "id": 1, "nome": 1,
            "dados_pessoais": 1, "contacto": 1, "titular2_data": 1,
        })

        clients = await cursor.to_list(length=10000)
        migrated_count = 0
        error_count = 0

        for client in clients:
            client_id = client.get("id")
            try:
                updates, _ = build_client_encryption_updates(client)
                if updates:
                    await db.clients.update_one(
                        {"id": client_id},
                        {"$set": updates},
                    )
                    migrated_count += 1
                    logger.info(
                        f"Migrado: {client_id} - {client.get('nome', 'Sem nome')}"
                    )
            except Exception as e:
                error_count += 1
                logger.error(f"Erro ao migrar {client_id}: {e}")

        await system_error_logger.log_error(
            error_type="migration_complete",
            message=(
                f"Migração RGPD concluída: {migrated_count} clientes migrados, "
                f"{error_count} erros"
            ),
            component="admin_migration",
            details={"migrated": migrated_count, "errors": error_count},
            severity="info",
            request_path="/api/admin/migration/run",
        )

        logger.info(
            f"MIGRAÇÃO CONCLUÍDA: {migrated_count} migrados, {error_count} erros"
        )

    except Exception as e:
        logger.error(f"Erro na migração: {e}")
        await system_error_logger.log_error(
            error_type="migration_error",
            message=f"Erro na migração RGPD: {e}",
            component="admin_migration",
            details={"error": str(e)},
            severity="error",
            request_path="/api/admin/migration/run",
        )
