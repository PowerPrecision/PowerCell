import os
import logging
import shutil
import asyncio
import tempfile
import zipfile
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone, timedelta
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME

logger = logging.getLogger(__name__)

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.environ.get("AWS_BUCKET_NAME")
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")


class BackupConfig:
    """Configuração do sistema de backup."""
    BACKUP_DIR = Path(tempfile.gettempdir()) / "creditoimo_backups"
    ONEDRIVE_BACKUP_FOLDER = os.environ.get("ONEDRIVE_BACKUP_FOLDER", "Backups")
    LOCAL_RETENTION_DAYS = int(os.environ.get("BACKUP_LOCAL_RETENTION_DAYS", "7"))
    CLOUD_RETENTION_DAYS = int(os.environ.get("BACKUP_CLOUD_RETENTION_DAYS", "30"))
    MAX_BACKUP_SIZE_MB = int(os.environ.get("BACKUP_MAX_SIZE_MB", "500"))


config = BackupConfig()


class BackupService:
    BACKUP_DIR = config.BACKUP_DIR

    def __init__(self):
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    async def create_backup(self):
        """Cria um backup completo da base de dados em JSON."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self.BACKUP_DIR / f"backup_{timestamp}"
        backup_path.mkdir(exist_ok=True)
        
        logger.info(f"Iniciando backup em: {backup_path}")
        
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        
        try:
            collections = await db.list_collection_names()
            count = 0
            
            for col_name in collections:
                cursor = db[col_name].find({})
                docs = await cursor.to_list(length=None)
                
                from bson import json_util
                
                file_path = backup_path / f"{col_name}.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_util.dumps(docs, indent=2))
                
                count += len(docs)
            
            shutil.make_archive(str(backup_path), 'zip', backup_path)
            zip_path = str(backup_path) + ".zip"
            
            shutil.rmtree(backup_path)
            
            logger.info(f"Backup concluído: {zip_path} ({count} documentos)")
            return zip_path
            
        except Exception as e:
            logger.error(f"Erro no backup: {e}")
            return None
        finally:
            client.close()


backup_service = BackupService()


def get_s3_client():
    """Cria cliente S3 com credenciais do ambiente."""
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME]):
        return None
    
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )


async def upload_backup_to_s3(zip_path: str) -> dict:
    """
    Upload backup para AWS S3.
    
    Args:
        zip_path: Caminho do ficheiro ZIP
        
    Returns:
        Dict com resultado do upload
    """
    result = {
        "success": False,
        "s3_key": None,
        "s3_url": None,
        "error": None
    }
    
    s3_client = get_s3_client()
    if not s3_client:
        result["error"] = "S3 não configurado (faltam credenciais AWS)"
        return result
    
    try:
        filename = Path(zip_path).name
        s3_key = f"backups/{filename}"
        
        # Upload com progresso
        s3_client.upload_file(
            zip_path,
            AWS_BUCKET_NAME,
            s3_key,
            ExtraArgs={'ContentType': 'application/zip'}
        )
        
        result["success"] = True
        result["s3_key"] = s3_key
        result["s3_url"] = f"s3://{AWS_BUCKET_NAME}/{s3_key}"
        
        logger.info(f"Backup uploaded to S3: {result['s3_url']}")
        return result
        
    except ClientError as e:
        result["error"] = f"Erro S3: {e.response['Error']['Message']}"
        logger.error(result["error"])
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Erro no upload S3: {e}")
        return result


async def cleanup_old_s3_backups(retention_days: int = None) -> dict:
    """
    Remove backups antigos do S3.
    
    Args:
        retention_days: Dias para manter (default: config.CLOUD_RETENTION_DAYS)
        
    Returns:
        Dict com resultado da limpeza
    """
    if retention_days is None:
        retention_days = config.CLOUD_RETENTION_DAYS
    
    result = {
        "deleted": 0,
        "errors": []
    }
    
    s3_client = get_s3_client()
    if not s3_client:
        return result
    
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        # Listar backups no S3
        response = s3_client.list_objects_v2(
            Bucket=AWS_BUCKET_NAME,
            Prefix='backups/'
        )
        
        if 'Contents' not in response:
            return result
        
        for obj in response['Contents']:
            if obj['LastModified'].replace(tzinfo=timezone.utc) < cutoff:
                try:
                    s3_client.delete_object(
                        Bucket=AWS_BUCKET_NAME,
                        Key=obj['Key']
                    )
                    result["deleted"] += 1
                    logger.info(f"Deleted old backup: {obj['Key']}")
                except Exception as e:
                    result["errors"].append(f"{obj['Key']}: {str(e)}")
        
        return result
        
    except Exception as e:
        result["errors"].append(str(e))
        return result


async def get_backup_statistics() -> dict:
    """
    Obtém estatísticas dos backups.
    
    Returns:
        Dict com estatísticas de backups
    """
    from database import db
    
    stats = {
        "total_backups": 0,
        "successful_backups": 0,
        "success_rate": 0,
        "total_size_bytes": 0,
        "last_backup": None
    }
    
    # Contar backups no histórico
    history = await db.backup_history.find({}).sort("started_at", -1).limit(100).to_list(100)
    
    stats["total_backups"] = len(history)
    stats["successful_backups"] = len([h for h in history if h.get("status") == "completed"])
    
    if stats["total_backups"] > 0:
        stats["success_rate"] = (stats["successful_backups"] / stats["total_backups"]) * 100
        stats["last_backup"] = {
            "started_at": history[0].get("started_at"),
            "status": history[0].get("status"),
            "success": history[0].get("status") == "completed"
        }
    
    # Calcular tamanho dos ficheiros locais
    if config.BACKUP_DIR.exists():
        for backup_file in config.BACKUP_DIR.glob("backup_*.zip"):
            stats["total_size_bytes"] += backup_file.stat().st_size
    
    return stats


async def full_backup_workflow(upload_to_cloud: bool = True, cleanup_after: bool = True) -> dict:
    """
    Executa o workflow completo de backup.
    
    1. Cria backup local
    2. (Opcional) Upload para S3
    3. (Opcional) Limpa backups antigos (local e cloud)
    
    Returns:
        Dict com resultado do backup
    """
    result = {
        "success": False,
        "backup_path": None,
        "size_bytes": 0,
        "uploaded": False,
        "s3_url": None,
        "cleaned_up": False,
        "error": None
    }
    
    try:
        # 1. Criar backup
        zip_path = await backup_service.create_backup()
        
        if not zip_path:
            result["error"] = "Falha ao criar backup"
            return result
        
        result["backup_path"] = zip_path
        result["size_bytes"] = Path(zip_path).stat().st_size
        result["success"] = True
        
        # 2. Upload para S3
        if upload_to_cloud:
            upload_result = await upload_backup_to_s3(zip_path)
            result["uploaded"] = upload_result["success"]
            result["s3_url"] = upload_result.get("s3_url")
            if not upload_result["success"]:
                logger.warning(f"Upload S3 falhou: {upload_result.get('error')}")
        
        # 3. Limpar backups antigos (local)
        if cleanup_after:
            cutoff = datetime.now() - timedelta(days=config.LOCAL_RETENTION_DAYS)
            for old_backup in config.BACKUP_DIR.glob("backup_*.zip"):
                try:
                    mtime = datetime.fromtimestamp(old_backup.stat().st_mtime)
                    if mtime < cutoff:
                        old_backup.unlink()
                        result["cleaned_up"] = True
                except Exception:
                    continue
            
            # Limpar S3 também
            if upload_to_cloud:
                await cleanup_old_s3_backups()
        
        return result
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Erro no workflow de backup: {e}")
        return result


# ====================================================================
# SCHEDULED BACKUP - Backup automático agendado
# ====================================================================

_scheduled_backup_running = False


async def scheduled_backup_job():
    """
    Job de backup agendado que corre periodicamente.
    Executa às 03:00 UTC diariamente.
    """
    global _scheduled_backup_running
    
    if _scheduled_backup_running:
        logger.warning("Scheduled backup já está a correr, ignorando...")
        return
    
    _scheduled_backup_running = True
    
    try:
        from database import db
        
        logger.info("[SCHEDULED BACKUP] Iniciando backup automático...")
        
        # Registar início
        await db.backup_history.insert_one({
            "triggered_by": "system",
            "triggered_by_email": "scheduled",
            "trigger_type": "scheduled",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running"
        })
        
        # Executar backup
        result = await full_backup_workflow(
            upload_to_cloud=True,
            cleanup_after=True
        )
        
        # Actualizar registo
        await db.backup_history.update_one(
            {"triggered_by": "system", "status": "running"},
            {"$set": {
                "status": "completed" if result["success"] else "failed",
                "result": result,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        if result["success"]:
            logger.info(f"[SCHEDULED BACKUP] Concluído com sucesso. S3: {result.get('s3_url')}")
        else:
            logger.error(f"[SCHEDULED BACKUP] Falhou: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"[SCHEDULED BACKUP] Erro: {e}")
    finally:
        _scheduled_backup_running = False


async def start_backup_scheduler():
    """
    Inicia o scheduler de backups automáticos.
    Corre em background e executa backup diário às 03:00 UTC.
    """
    logger.info("[BACKUP SCHEDULER] Iniciado - backup diário às 03:00 UTC")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # Calcular próxima execução às 03:00 UTC
            next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"[BACKUP SCHEDULER] Próximo backup em {wait_seconds/3600:.1f}h ({next_run.isoformat()})")
            
            await asyncio.sleep(wait_seconds)
            
            # Executar backup
            await scheduled_backup_job()
            
            # Pequena pausa para evitar execução dupla
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("[BACKUP SCHEDULER] Encerrado")
            break
        except Exception as e:
            logger.error(f"[BACKUP SCHEDULER] Erro: {e}")
            await asyncio.sleep(3600)  # Esperar 1h em caso de erro