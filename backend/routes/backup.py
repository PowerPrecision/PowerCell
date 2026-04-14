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
