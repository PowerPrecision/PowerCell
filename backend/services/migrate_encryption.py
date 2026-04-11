"""
====================================================================
SCRIPT DE MIGRAÇÃO - ENCRIPTAÇÃO DE CAMPOS SENSÍVEIS
====================================================================
Encripta campos sensíveis (NIFs, documentos, senhas) em processos
existentes na base de dados.

Uso:
    python -m services.migrate_encryption [--dry-run] [--batch-size 100]
    
Opções:
    --dry-run     Simula a migração sem guardar alterações
    --batch-size  Número de documentos por batch (default: 100)
====================================================================
"""
import asyncio
import argparse
import logging
from datetime import datetime, timezone

from database import db
from services.encryption import encryption_service, SENSITIVE_FIELDS

logger = logging.getLogger(__name__)


async def migrate_processes_encryption(dry_run: bool = False, batch_size: int = 100) -> dict:
    """
    Migra processos para usar encriptação em campos sensíveis.
    
    Args:
        dry_run: Se True, não guarda alterações
        batch_size: Número de documentos por batch
        
    Returns:
        Estatísticas da migração
    """
    if not encryption_service.is_available():
        return {
            "success": False,
            "error": "Serviço de encriptação não disponível",
            "total": 0,
            "migrated": 0,
            "skipped": 0,
            "errors": []
        }
    
    stats = {
        "success": True,
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "already_encrypted": 0,
        "errors": []
    }
    
    # Contar total de processos
    total = await db.processes.count_documents({})
    stats["total"] = total
    
    logger.info(f"Iniciando migração de {total} processos (dry_run={dry_run})")
    
    # Processar em batches
    skip = 0
    while skip < total:
        batch = await db.processes.find({}).skip(skip).limit(batch_size).to_list(batch_size)
        
        for process in batch:
            try:
                process_id = process.get("id")
                needs_update = False
                updated_process = process.copy()
                
                # Verificar campos no nível raiz
                for field in SENSITIVE_FIELDS.get("root", []):
                    if field in process and process[field]:
                        if not encryption_service.is_encrypted(str(process[field])):
                            updated_process[field] = encryption_service.encrypt(str(process[field]))
                            needs_update = True
                
                # Verificar sub-dicionários
                for section, fields in SENSITIVE_FIELDS.items():
                    if section == "root":
                        continue
                    
                    if section in process and isinstance(process[section], dict):
                        for field in fields:
                            if field in process[section] and process[section][field]:
                                if not encryption_service.is_encrypted(str(process[section][field])):
                                    if section not in updated_process:
                                        updated_process[section] = {}
                                    updated_process[section][field] = encryption_service.encrypt(
                                        str(process[section][field])
                                    )
                                    needs_update = True
                
                # Verificar listas de co-compradores
                for list_field in ["co_buyers", "co_applicants"]:
                    if list_field in process and isinstance(process[list_field], list):
                        fields_to_encrypt = SENSITIVE_FIELDS.get(list_field, [])
                        for i, item in enumerate(process[list_field]):
                            if isinstance(item, dict):
                                for field in fields_to_encrypt:
                                    if field in item and item[field]:
                                        if not encryption_service.is_encrypted(str(item[field])):
                                            if list_field not in updated_process:
                                                updated_process[list_field] = process[list_field].copy()
                                            updated_process[list_field][i][field] = encryption_service.encrypt(
                                                str(item[field])
                                            )
                                            needs_update = True
                
                if needs_update:
                    if not dry_run:
                        # Adicionar timestamp de migração
                        updated_process["encryption_migrated_at"] = datetime.now(timezone.utc).isoformat()
                        
                        # Actualizar na base de dados
                        await db.processes.update_one(
                            {"id": process_id},
                            {"$set": updated_process}
                        )
                    
                    stats["migrated"] += 1
                else:
                    stats["already_encrypted"] += 1
                
            except Exception as e:
                stats["errors"].append({
                    "process_id": process.get("id"),
                    "error": str(e)
                })
                stats["skipped"] += 1
        
        skip += batch_size
        logger.info(f"Processados {min(skip, total)}/{total} processos...")
    
    logger.info(f"Migração concluída: {stats}")
    return stats


async def migrate_clients_encryption(dry_run: bool = False, batch_size: int = 100) -> dict:
    """
    Migra clientes (users) para usar encriptação em campos sensíveis.
    """
    stats = {
        "success": True,
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": []
    }
    
    if not encryption_service.is_available():
        return stats
    
    # Campos sensíveis em utilizadores
    user_sensitive_fields = ["phone", "nif"]
    
    total = await db.users.count_documents({})
    stats["total"] = total
    
    skip = 0
    while skip < total:
        batch = await db.users.find({}).skip(skip).limit(batch_size).to_list(batch_size)
        
        for user in batch:
            try:
                needs_update = False
                update_data = {}
                
                for field in user_sensitive_fields:
                    if field in user and user[field]:
                        if not encryption_service.is_encrypted(str(user[field])):
                            update_data[field] = encryption_service.encrypt(str(user[field]))
                            needs_update = True
                
                if needs_update and not dry_run:
                    update_data["encryption_migrated_at"] = datetime.now(timezone.utc).isoformat()
                    await db.users.update_one(
                        {"id": user.get("id")},
                        {"$set": update_data}
                    )
                    stats["migrated"] += 1
                
            except Exception as e:
                stats["errors"].append({
                    "user_id": user.get("id"),
                    "error": str(e)
                })
                stats["skipped"] += 1
        
        skip += batch_size
    
    return stats


async def main():
    parser = argparse.ArgumentParser(description="Migração de encriptação de dados sensíveis")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem guardar")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--clients", action="store_true", help="Migrar também clientes")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("MIGRAÇÃO DE ENCRIPTAÇÃO DE CAMPOS SENSÍVEIS")
    print("=" * 60)
    print(f"Modo: {'DRY RUN (sem alterações)' if args.dry_run else 'PRODUÇÃO'}")
    print(f"Batch size: {args.batch_size}")
    print()
    
    # Migrar processos
    print("Migrando processos...")
    process_stats = await migrate_processes_encryption(
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )
    print(f"Processos: {process_stats['migrated']} migrados, {process_stats['already_encrypted']} já encriptados")
    
    # Migrar clientes se solicitado
    if args.clients:
        print("\nMigrando clientes...")
        client_stats = await migrate_clients_encryption(
            dry_run=args.dry_run,
            batch_size=args.batch_size
        )
        print(f"Clientes: {client_stats['migrated']} migrados")
    
    print("\n" + "=" * 60)
    print("MIGRAÇÃO CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
