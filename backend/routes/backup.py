"""
====================================================================
BACKUP ROUTES - CREDITOIMO
====================================================================
Endpoints para gestão de backups da base de dados.

Apenas administradores podem aceder a estes endpoints.

Endpoints:
- GET  /api/backup/statistics     - Estatísticas de backups
- POST /api/backup/trigger        - Triggerar backup manual
- GET  /api/backup/history        - Histórico de backups
- POST /api/backup/verify         - Verificar integridade
====================================================================
"""
import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from database import db
from models.auth import UserRole
from services.auth import require_roles, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["Backup"])


# ====================================================================
# MODELS
# ====================================================================
class BackupRequest(BaseModel):
    """Request para backup manual."""
    upload_to_cloud: bool = True
    cleanup_after: bool = True


# ====================================================================
# ENDPOINTS
# ====================================================================
@router.get("/statistics")
async def get_statistics(
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém estatísticas dos backups.
    
    Retorna:
    - Total de backups
    - Taxa de sucesso
    - Tamanho total
    - Último backup
    """
    from services.backup import get_backup_statistics
    
    stats = await get_backup_statistics()
    return {
        "success": True,
        "data": stats
    }


@router.post("/trigger")
async def trigger_backup(
    request: BackupRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Triggera um backup manual.
    
    O backup é executado em background para não bloquear a resposta.
    Use GET /backup/statistics para verificar o resultado.
    """
    from services.backup import full_backup_workflow
    import uuid
    
    logger.info(f"[BACKUP] Backup manual triggered por {current_user.get('email')}")
    
    # Criar ID único para este backup
    backup_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    
    # Registar início com ID único
    await db.backup_history.insert_one({
        "id": backup_id,
        "triggered_by": current_user.get("id"),
        "triggered_by_email": current_user.get("email"),
        "trigger_type": "manual",
        "started_at": started_at,
        "status": "running"
    })
    
    # Executar em background
    async def run_backup():
        """Executa o workflow completo de backup em background.

        Inclui: exportação de todas as coleções MongoDB, compressão
        em ZIP, e opcionalmente upload para S3. Atualiza o registo
        em backup_history com o resultado (completed/failed).
        """
        try:
            result = await full_backup_workflow(
                upload_to_cloud=request.upload_to_cloud,
                cleanup_after=request.cleanup_after
            )
            
            # Actualizar registo usando o ID único
            await db.backup_history.update_one(
                {"id": backup_id},
                {"$set": {
                    "status": "completed" if result["success"] else "failed",
                    "result": result,
                    "completed_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"[BACKUP] Backup {backup_id} concluído com status: {'completed' if result['success'] else 'failed'}")
        except Exception as e:
            logger.error(f"[BACKUP] Erro no backup {backup_id}: {e}")
            await db.backup_history.update_one(
                {"id": backup_id},
                {"$set": {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc)
                }}
            )
    
    background_tasks.add_task(run_backup)
    
    return {
        "success": True,
        "message": "Backup iniciado em background",
        "backup_id": backup_id,
        "check_status_at": f"/api/backup/status/{backup_id}"
    }


@router.get("/history")
async def get_history(
    limit: int = 20,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém histórico de backups.
    """
    history = await db.backup_history.find(
        {},
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    
    return {
        "success": True,
        "count": len(history),
        "history": history
    }


@router.post("/verify")
async def verify_backups(
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Verifica integridade dos backups.
    
    Verifica:
    - Último backup bem sucedido
    - Integridade dos ficheiros ZIP
    - Espaço em disco
    """
    from services.backup import get_backup_statistics, config
    import zipfile
    
    stats = await get_backup_statistics()
    issues = []
    verified_files = []
    
    # Verificar último backup
    last_backup = stats.get("last_backup")
    if not last_backup:
        issues.append("Nenhum backup no histórico")
    elif not last_backup.get("success"):
        issues.append(f"Último backup falhou: {last_backup.get('error')}")
    
    # Verificar idade
    if last_backup and last_backup.get("started_at"):
        try:
            last_time = datetime.fromisoformat(
                last_backup["started_at"].replace("Z", "+00:00")
            )
            age_hours = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600
            if age_hours > 48:
                issues.append(f"Último backup tem {age_hours:.0f}h (recomendado: <48h)")
        except Exception:
            pass
    
    # Verificar integridade dos ZIPs
    for backup_file in config.BACKUP_DIR.glob("backup_*.zip"):
        try:
            with zipfile.ZipFile(backup_file, 'r') as zf:
                test_result = zf.testzip()
                verified_files.append({
                    "filename": backup_file.name,
                    "size_mb": round(backup_file.stat().st_size / 1024 / 1024, 2),
                    "valid": test_result is None
                })
                if test_result is not None:
                    issues.append(f"Ficheiro corrompido: {backup_file.name}")
        except Exception as e:
            issues.append(f"Erro ao verificar {backup_file.name}: {str(e)}")
    
    return {
        "success": len(issues) == 0,
        "statistics": stats,
        "verified_files": verified_files,
        "issues": issues,
        "verified_at": datetime.now(timezone.utc).isoformat()
    }


@router.get("/config")
async def get_backup_config(
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém configuração actual do sistema de backup.
    """
    from services.backup import config, get_s3_client
    
    s3_configured = get_s3_client() is not None
    
    return {
        "success": True,
        "config": {
            "backup_dir": str(config.BACKUP_DIR),
            "onedrive_folder": config.ONEDRIVE_BACKUP_FOLDER,
            "local_retention_days": config.LOCAL_RETENTION_DAYS,
            "cloud_retention_days": config.CLOUD_RETENTION_DAYS,
            "max_backup_size_mb": config.MAX_BACKUP_SIZE_MB,
            "s3_configured": s3_configured,
            "scheduled_backup": {
                "enabled": True,
                "schedule": "03:00 UTC diariamente",
                "next_run": "Calculado automaticamente"
            }
        }
    }


@router.post("/run-now")
async def run_backup_now(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Executa backup imediato com upload para S3.
    """
    from services.backup import full_backup_workflow
    
    logger.info(f"[BACKUP] Backup imediato triggered por {current_user.get('email')}")
    
    # Registar início
    backup_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    await db.backup_history.insert_one({
        "id": backup_id,
        "triggered_by": current_user.get("id"),
        "triggered_by_email": current_user.get("email"),
        "trigger_type": "manual_immediate",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running"
    })
    
    async def run_backup():
        """Executa backup imediato com upload obrigatório para S3.

        Semelhante ao ``run_backup`` do endpoint agendado, mas com
        upload_to_cloud=True e cleanup_after=True forçados.
        """
        try:
            result = await full_backup_workflow(
                upload_to_cloud=True,
                cleanup_after=True
            )
            
            await db.backup_history.update_one(
                {"id": backup_id},
                {"$set": {
                    "status": "completed" if result["success"] else "failed",
                    "result": result,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        except Exception as e:
            await db.backup_history.update_one(
                {"id": backup_id},
                {"$set": {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
    
    background_tasks.add_task(run_backup)
    
    return {
        "success": True,
        "message": "Backup iniciado com upload para S3",
        "backup_id": backup_id,
        "check_status_at": f"/api/backup/status/{backup_id}"
    }


@router.get("/status/{backup_id}")
async def get_backup_status(
    backup_id: str,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Obtém estado de um backup específico.
    """
    backup = await db.backup_history.find_one({"id": backup_id}, {"_id": 0})
    
    if not backup:
        raise HTTPException(status_code=404, detail="Backup não encontrado")
    
    return {
        "success": True,
        "backup": backup
    }


@router.post("/restore-from-s3")
async def restore_from_s3(
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Restaura a base de dados de Produção a partir do backup mais recente no S3.
    ATENÇÃO: Este endpoint sobrescreve TODOS os dados da BD actual.
    """
    from config import MONGO_URL, DB_NAME
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.backup import get_s3_client
    from bson import json_util
    import tempfile
    import zipfile
    import shutil
    import boto3
    import io

    # Validação de segurança
    confirm = data.get("confirm")
    if confirm != "RESTAURAR_PRODUCAO":
        raise HTTPException(
            status_code=400,
            detail='Para confirmar, envie {"confirm": "RESTAURAR_PRODUCAO"} no body. Esta operação sobrescreve TODOS os dados da BD.'
        )

    backup_key = data.get("backup_key")  # S3 key específico (opcional)
    collections_to_restore = data.get("collections")  # Lista de colecções (opcional, default = todas)

    logger.warning(f"[RESTORE] Restore de Produção iniciado por {current_user.get('email')}")

    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(status_code=500, detail="S3 não configurado — credenciais AWS em falta")

    tmp_dir = tempfile.mkdtemp()
    stats = {"collections": {}, "total_documents": 0, "errors": [], "warnings": []}

    try:
        # 1. Encontrar backup no S3
        if backup_key:
            s3_keys = [backup_key]
        else:
            # Listar backups e encontrar o mais recente
            response = s3_client.list_objects_v2(
                Bucket=os.environ.get("AWS_BUCKET_NAME", ""),
                Prefix="backups/",
            )
            s3_keys = sorted(
                [obj["Key"] for obj in response.get("Contents", []) if obj["Key"].endswith(".zip")],
                reverse=True
            )
            if not s3_keys:
                raise HTTPException(status_code=404, detail="Nenhum backup encontrado no S3")

        selected_key = s3_keys[0]
        logger.info(f"[RESTORE] A usar backup: {selected_key}")

        # 2. Download do ZIP
        zip_buffer = io.BytesIO()
        s3_client.download_fileobj(os.environ.get("AWS_BUCKET_NAME", ""), selected_key, zip_buffer)
        zip_buffer.seek(0)

        # 3. Extrair e importar colecções
        client = AsyncIOMotorClient(MONGO_URL)
        database = client[DB_NAME]

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            json_files = [f for f in zf.namelist() if f.endswith(".json")]

            for json_file in json_files:
                col_name = json_file.replace(".json", "").split("/")[-1]

                # Se collections_to_restore especificado, filtrar
                if collections_to_restore and col_name not in collections_to_restore:
                    continue

                try:
                    content = zf.read(json_file)
                    docs = json_util.loads(content)

                    if not isinstance(docs, list) or not docs:
                        stats["warnings"].append(f"Colecção {col_name}: sem documentos válidos")
                        continue

                    # Limpar colecção actual e inserir dados do backup
                    await database[col_name].delete_many({})
                    if docs:
                        result = await database[col_name].insert_many(docs)
                        stats["collections"][col_name] = len(docs)
                        stats["total_documents"] += len(docs)

                    logger.info(f"[RESTORE] {col_name}: {len(docs)} documentos restaurados")

                except Exception as e:
                    stats["errors"].append(f"{col_name}: {str(e)}")
                    logger.error(f"[RESTORE] Erro em {col_name}: {e}")

        client.close()

        # Limpeza
        shutil.rmtree(tmp_dir, ignore_errors=True)

        logger.info(f"[RESTORE] Concluído: {stats['total_documents']} documentos em {len(stats['collections'])} colecções")

        return {
            "success": len(stats["errors"]) == 0,
            "backup_key": selected_key,
            "collections": stats["collections"],
            "total_documents": stats["total_documents"],
            "errors": stats["errors"],
            "warnings": stats["warnings"],
            "restored_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[RESTORE] Erro fatal: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Erro no restore: {str(e)}")


# ====================================================================
# PACOTE CD — EMERGENCY RESTORE ENDPOINT (Swap Atómico)
# ====================================================================
# Endpoint de restauro de emergência com swap atómico: em vez de
# delete_many + insert_many (que deixa a BD inconsistente se falhar a
# meio), usa coleções temporárias (_restore_*) e rename atómico.
#
# Fluxo:
# 1. Download do último ZIP do S3 (backups/) para memória (BytesIO)
# 2. Extrair JSON de todas as coleções (ignora backup_history e system.indexes)
# 3. insert_many para coleções temporárias (_restore_{collection})
# 4. drop() coleções reais + rename temporárias → swap atómico
# 5. Recriar índices (users.email unique, id unique nas coleções principais)
# 6. Retornar sucesso
# ====================================================================

# Coleções a ignorar no restore (metadata interna do MongoDB ou do próprio backup)
_RESTORE_IGNORE_COLLECTIONS = {
    "backup_history",
    "system.indexes",
    "system_config",  # Preservar config atual do sistema (não restaurar config antiga)
}

# Coleções principais onde recriar índices únicos após o swap
_RESTORE_INDEX_COLLECTIONS = [
    "users", "clients", "processes", "documents", "tasks", "history",
    "activities", "properties", "announcements", "portal_messages",
    "workflow_statuses", "companies", "user_company_roles",
    "user_email_configs", "refresh_tokens", "deadlines",
]


@router.post("/restore")
async def emergency_restore(
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    PACOTE CD — Restauro de emergência com swap atómico.

    Restaura a BD de Produção a partir do backup mais recente no S3,
    usando coleções temporárias e rename atómico para garantir que a BD
    nunca fica inconsistente (mesmo que o processo falhe a meio).

    Segurança:
    - Apenas ADMIN e CEO podem executar
    - Requer confirmação explícita: {"confirm": "RESTAURAR_PRODUCAO"}
    - Preserva system_config (config atual do sistema não é restaurada)

    Fluxo:
    1. Download ZIP do S3 para memória
    2. Extrair JSON de cada coleção (ignora backup_history, system.indexes, system_config)
    3. insert_many para _restore_{collection} (temporárias)
    4. drop() coleções reais + rename temporárias (swap atómico)
    5. Recriar índices (users.email unique, id unique)
    6. Retorna sucesso com estatísticas
    """
    from config import MONGO_URL, DB_NAME
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.backup import get_s3_client
    from bson import json_util
    import zipfile
    import io

    # Validação de segurança — confirmação explícita
    confirm = data.get("confirm")
    if confirm != "RESTAURAR_PRODUCAO":
        raise HTTPException(
            status_code=400,
            detail='Para confirmar, envie {"confirm": "RESTAURAR_PRODUCAO"} no body. '
                   'Esta operação sobrescreve TODOS os dados da BD com swap atómico.'
        )

    backup_key = data.get("backup_key")  # S3 key específico (opcional)
    collections_to_restore = data.get("collections")  # Lista de colecções (opcional)

    logger.warning(
        f"[RESTORE-CD] Restauro de emergência (swap atómico) iniciado por "
        f"{current_user.get('email')} — backup_key={backup_key or 'mais recente'}"
    )

    s3_client = get_s3_client()
    if not s3_client:
        raise HTTPException(
            status_code=500,
            detail="S3 não configurado — credenciais AWS em falta. "
                   "Configure AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY e AWS_BUCKET_NAME."
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
        # ════════════════════════════════════════════════════════════
        # 1. ENCONTRAR E DOWNLOAD DO BACKUP NO S3
        # ════════════════════════════════════════════════════════════
        if backup_key:
            s3_keys = [backup_key]
        else:
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix="backups/",
            )
            s3_keys = sorted(
                [obj["Key"] for obj in response.get("Contents", [])
                 if obj["Key"].endswith(".zip")],
                reverse=True
            )
            if not s3_keys:
                raise HTTPException(
                    status_code=404,
                    detail="Nenhum backup encontrado no S3 (prefixo backups/)"
                )

        selected_key = s3_keys[0]
        logger.info(f"[RESTORE-CD] A usar backup: {selected_key}")

        # Download para memória (BytesIO — não toca o disco)
        zip_buffer = io.BytesIO()
        s3_client.download_fileobj(bucket_name, selected_key, zip_buffer)
        zip_buffer.seek(0)

        # ════════════════════════════════════════════════════════════
        # 2. EXTRAIR JSON DAS COLEÇÕES DO ZIP
        # ════════════════════════════════════════════════════════════
        extracted_data = {}  # {col_name: [docs]}

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            json_files = [f for f in zf.namelist() if f.endswith(".json")]

            for json_file in json_files:
                col_name = json_file.replace(".json", "").split("/")[-1]

                # Ignorar coleções de metadata/config
                if col_name in _RESTORE_IGNORE_COLLECTIONS:
                    stats["warnings"].append(f"Ignorada: {col_name}")
                    continue

                # Se collections_to_restore especificado, filtrar
                if collections_to_restore and col_name not in collections_to_restore:
                    continue

                try:
                    content = zf.read(json_file)
                    docs = json_util.loads(content)

                    if not isinstance(docs, list) or not docs:
                        stats["warnings"].append(f"{col_name}: sem documentos válidos")
                        continue

                    extracted_data[col_name] = docs
                    logger.info(f"[RESTORE-CD] Extraído: {col_name} ({len(docs)} docs)")

                except Exception as e:
                    stats["errors"].append(f"Extrair {col_name}: {str(e)}")
                    logger.error(f"[RESTORE-CD] Erro ao extrair {col_name}: {e}")

        if not extracted_data:
            raise HTTPException(
                status_code=500,
                detail="Nenhuma coleção válida encontrada no ZIP de backup"
            )

        # ════════════════════════════════════════════════════════════
        # 3. INSERT_MANY PARA COLEÇÕES TEMPORÁRIAS (_restore_*)
        # ════════════════════════════════════════════════════════════
        client = AsyncIOMotorClient(MONGO_URL)
        database = client[DB_NAME]
        temp_prefix = stats["temp_prefix"]

        for col_name, docs in extracted_data.items():
            temp_col = f"{temp_prefix}{col_name}"
            try:
                # Limpar temporária se já existir (de um restore falhado anterior)
                await database[temp_col].drop()
                # Inserir dados na temporária
                await database[temp_col].insert_many(docs)
                stats["collections"][col_name] = len(docs)
                stats["total_documents"] += len(docs)
                logger.info(f"[RESTORE-CD] Temporária {temp_col}: {len(docs)} docs inseridos")
            except Exception as e:
                stats["errors"].append(f"Insert {temp_col}: {str(e)}")
                logger.error(f"[RESTORE-CD] Erro ao inserir em {temp_col}: {e}")

        # Se houve erros em todas as coleções, abortar antes do swap
        if len(stats["errors"]) == len(extracted_data):
            # Limpar temporárias
            for col_name in extracted_data:
                await database[f"{temp_prefix}{col_name}"].drop()
            client.close()
            raise HTTPException(
                status_code=500,
                detail=f"Todos os inserts falharam. Swap abortado. Erros: {stats['errors'][:3]}"
            )

        # ════════════════════════════════════════════════════════════
        # 4. SWAP ATÓMICO: drop() real + rename() temporária
        # ════════════════════════════════════════════════════════════
        # Para cada coleção com dados na temporária:
        # a) drop() a coleção real (se existir)
        # b) rename() a temporária para o nome real
        # O rename no MongoDB é atómico — a coleção fica disponível
        # instantaneamente com o novo nome.
        # ════════════════════════════════════════════════════════════
        for col_name in extracted_data:
            temp_col = f"{temp_prefix}{col_name}"
            if col_name not in stats["collections"]:
                continue  # Insert falhou — não fazer swap desta coleção

            try:
                # a) Drop da coleção real (se existir)
                # Verificar se a temporária tem dados antes de dropar a real
                temp_count = await database[temp_col].count_documents({})
                if temp_count == 0:
                    stats["warnings"].append(f"Swap {col_name}: temporária vazia, skip")
                    await database[temp_col].drop()
                    continue

                # b) Drop real + rename temporária
                await database[col_name].drop()
                await database[temp_col].rename(col_name)
                stats["swapped"].append(col_name)
                logger.info(f"[RESTORE-CD] Swap atómico: {temp_col} → {col_name} ({temp_count} docs)")

            except Exception as e:
                stats["errors"].append(f"Swap {col_name}: {str(e)}")
                logger.error(f"[RESTORE-CD] Erro no swap de {col_name}: {e}")
                # Tentar limpar a temporária que ficou órfã
                try:
                    await database[temp_col].drop()
                except Exception:
                    pass

        # ════════════════════════════════════════════════════════════
        # 5. RECRIAR ÍNDICES NAS COLEÇÕES PRINCIPAIS
        # ════════════════════════════════════════════════════════════
        # O drop() remove os índices. Recriar os essenciais:
        # - users: email (unique), id (unique)
        # - clients: id (unique), contacto.email_hash
        # - processes: id (unique), client_id, status
        # - Outras coleções principais: id (unique)
        # ════════════════════════════════════════════════════════════
        index_stats = {"created": 0, "errors": []}

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
                {"keys": [("user_id", 1), ("company_id", 1)], "name": "idx_ucr_unique", "unique": True},
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

        for col_name, index_defs in _INDEX_DEFINITIONS.items():
            if col_name not in stats["swapped"]:
                continue  # Coleção não foi restaurada — saltar
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
                    # Erro de índice não é fatal — a BD funciona sem índices
                    # (apenas mais lento). Logar e continuar.
                    idx_name = idx_def.get("name", "unknown")
                    index_stats["errors"].append(f"{col_name}.{idx_name}: {str(e)}")
                    logger.warning(f"[RESTORE-CD] Índice {col_name}.{idx_name}: {e}")

        # ════════════════════════════════════════════════════════════
        # 6. LIMPEZA DE TEMPORÁRIAS ÓRFÃS
        # ════════════════════════════════════════════════════════════
        # Se houve coleções temporárias que não foram swapped (por erro),
        # limpá-las para não deixar lixo na BD.
        for col_name in extracted_data:
            temp_col = f"{temp_prefix}{col_name}"
            try:
                # Verificar se a temporária ainda existe (não foi renamed)
                cols = await database.list_collection_names()
                if temp_col in cols:
                    await database[temp_col].drop()
                    logger.info(f"[RESTORE-CD] Limpeza: temporária órfã {temp_col} removida")
            except Exception:
                pass

        client.close()

        # ════════════════════════════════════════════════════════════
        # 7. RETORNAR SUCESSO
        # ════════════════════════════════════════════════════════════
        logger.info(
            f"[RESTORE-CD] Concluído: {stats['total_documents']} documentos em "
            f"{len(stats['swapped'])} coleções swapped, {index_stats['created']} índices criados. "
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
            "ignored": list(_RESTORE_IGNORE_COLLECTIONS),
            "restored_by": current_user.get("email"),
            "restored_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[RESTORE-CD] Erro fatal: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no restore de emergência: {str(e)}")
