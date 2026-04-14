"""
====================================================================
SERVIÇO DE BACKUP — CREDITOIMO
====================================================================
Sistema de backup completo da base de dados MongoDB com archive para S3.

ARQUITECTURA DE BACKUP:
1. Exportação local: Cada coleção MongoDB é exportada como um ficheiro JSON
   individual (usando ``bson.json_util`` para preservar ObjectId, datetime e
   outros tipos BSON nativos). Todos os JSONs são comprimidos num único ZIP
   com timestamp UTC.
2. Upload para S3: O ZIP local é carregado para o bucket S3 sob o prefixo
   ``backups/``, servindo como repositório autoritativo de disaster recovery.
3. Retenção: Backups locais são mantidos por 7 dias; backups S3 por 30 dias.
   A retenção cloud mais longa reflete o facto de o S3 ser o fallback final
   em caso de falha total do servidor.

PORQUÊ ZIP COM JSON POR COLEÇÃO:
- Um JSON por coleção permite restaurações granulares (restaurar apenas
  ``processes`` sem tocar em ``users``).
- O ZIP reduz significativamente o tamanho (JSONs de texto comprimem bem).
- ``bson.json_util`` preserva tipos BSON que ``json.dumps`` padrão perderia,
  evitando corrupção de ObjectId ou datas durante o restauro.

CONFIGURAÇÃO:
- Variáveis de ambiente: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
  AWS_BUCKET_NAME, AWS_REGION.
- Retenção configurável via: BACKUP_LOCAL_RETENTION_DAYS,
  BACKUP_CLOUD_RETENTION_DAYS, BACKUP_MAX_SIZE_MB.
====================================================================
"""
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
    """
    Configuração centralizada do sistema de backup.

    Define períodos de retenção (local vs. cloud), tamanho máximo e
    diretório de armazenamento local. Os valores podem ser
    sobrescritos por variáveis de ambiente, permitindo configurar
    políticas distintas para ambientes de Dev e Produção.

    A retenção cloud (30 dias) é mais longa que a local (7 dias) porque
    o S3 é o repositório de_backup autoritativo em caso de desastre.
    """
    BACKUP_DIR = Path(tempfile.gettempdir()) / "creditoimo_backups"
    ONEDRIVE_BACKUP_FOLDER = os.environ.get("ONEDRIVE_BACKUP_FOLDER", "Backups")
    LOCAL_RETENTION_DAYS = int(os.environ.get("BACKUP_LOCAL_RETENTION_DAYS", "7"))
    CLOUD_RETENTION_DAYS = int(os.environ.get("BACKUP_CLOUD_RETENTION_DAYS", "30"))
    MAX_BACKUP_SIZE_MB = int(os.environ.get("BACKUP_MAX_SIZE_MB", "500"))


config = BackupConfig()


class BackupService:
    """Serviço de backup da base de dados MongoDB.

    Responsável por exportar todas as coleções MongoDB para ficheiros JSON,
    comprimir num ZIP com timestamp UTC e guardar no diretório local de backup.

    O serviço é inicializado como singleton (``backup_service``) e usa um
    ``AsyncIOMotorClient`` dedicado (não partilha a ligação da aplicação)
    para evitar interferir com as operações normais da API durante o dump.

    A exportação usa ``bson.json_util.dumps`` em vez de ``json.dumps`` para
    preservar tipos BSON nativos (ObjectId, datetime, Binary) sem perda.
    """

    BACKUP_DIR = config.BACKUP_DIR

    def __init__(self):
        """Inicializa o diretório de backup local.

        Cria ``BACKUP_DIR`` se não existir. O diretório usa o tempdir do
        sistema operativo por padrão, permitindo múltiplas instâncias da
        aplicação em ambientes cloud (Vercel, Railway, etc.) sem conflitos.
        """
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    async def create_backup(self):
        """
        Cria um backup completo da base de dados, exportando todas as colecções
        para ficheiros JSON individuais comprimidos num ZIP.

        Este é o primeiro passo do pipeline de disaster recovery — sem backup local,
        não há ponto de restauro caso o MongoDB de Produção fique indisponível.
        A exportação por coleção (um JSON por coleção) permite restaurações
        granulares e diagnósticos mais fáceis em caso de corrupção parcial.

        Usa bson.json_util para preservar tipos BSON nativos (ObjectId, datetime)
        sem perda de informação. O ZIP final é guardado em BACKUP_DIR com timestamp
        UTC para ordenação cronológica.

        Returns:
            str: Caminho absoluto do ficheiro ZIP, ou None em caso de erro.

        Raises:
            RuntimeError: Se não for possível ligar ao MongoDB ou listar colecções.
        """
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
    """Cria cliente S3 com credenciais do ambiente.

    Verifica se todas as credenciais necessárias (AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY, AWS_BUCKET_NAME) estão definidas antes de
    criar o cliente. Retorna ``None`` silenciosamente se faltar alguma —
    isto permite que o sistema funcione em modo "backup local only" quando
    o S3 não está configurado (ex: ambientes de desenvolvimento).

    Returns:
        boto3.client | None: Cliente S3 configurado, ou None se faltar
            credenciais.
    """
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
        Carrega um ficheiro ZIP de backup para o bucket S3 da organização.

        O S3 é o repositório de backup autoritativo para disaster recovery.
        Mesmo que o servidor de aplicação falhe completamente, os backups
        persistem na cloud com retenção de 30 dias (config.CLOUD_RETENTION_DAYS).

        O ficheiro é colocado sob o prefixo ``backups/`` com o nome original
        (contém timestamp UTC), garantindo ordem cronológica e unicidade.

        Args:
            zip_path: Caminho absoluto do ficheiro ZIP local gerado por
                ``BackupService.create_backup``.

        Returns:
            dict: Resultado da operação com as chaves:
                - success (bool): True se o upload foi concluído com sucesso.
                - s3_key (str | None): Chave S3 (ex: ``backups/backup_20250101_030000.zip``).
                - s3_url (str | None): URL S3 completa (ex: ``s3://bucket/backups/...``).
                - error (str | None): Mensagem de erro se success=False.

        Raises:
            ClientError: Se as credenciais AWS forem inválidas ou o bucket não existir.
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
    """Remove backups antigos do S3, respeitando a política de retenção.

    Esta função complementa ``cleanup_old_s3_backups`` do workflow — enquanto
    o workflow limpa backups locais (sistema de ficheiros), esta função limpa
    backups na cloud. A retenção cloud (30 dias) é deliberadamente mais longa
    que a local (7 dias) porque o S3 é o repositório de disaster recovery.

    Args:
        retention_days: Dias para manter (default: config.CLOUD_RETENTION_DAYS
            que é 30). Permite executar limpezas agressivas passando um valor
            menor (ex: 7 para teste).

    Returns:
        dict: Resultado da limpeza com chaves:
            - deleted (int): Número de backups removidos.
            - errors (list[str]): Lista de erros (se houver).
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
    """Obtém estatísticas agregadas dos backups (local + histórico na BD).

    Consulta a coleção ``backup_history`` para calcular taxa de sucesso e
    informação do último backup. Calcula também o tamanho total dos ficheiros
    locais de backup.

    Returns:
        dict: Estatísticas com chaves:
            - total_backups (int): Total de backups registados.
            - successful_backups (int): Total com status "completed".
            - success_rate (float): Percentagem de backups bem sucedidos.
            - total_size_bytes (int): Soma do tamanho dos ZIPs locais.
            - last_backup (dict | None): Informação do backup mais recente.
    """
    from database import db
    
    stats = {
        "total_backups": 0,
        "successful_backups": 0,
        "success_rate": 0,
        "total_size_bytes": 0,
        "last_backup": None
    }
    
    try:
        # Contar backups no histórico - ordenar por started_at descendente
        history = await db.backup_history.find({}).sort("started_at", -1).limit(100).to_list(100)
        
        stats["total_backups"] = len(history)
        stats["successful_backups"] = len([h for h in history if h.get("status") == "completed"])
        
        if stats["total_backups"] > 0:
            stats["success_rate"] = (stats["successful_backups"] / stats["total_backups"]) * 100
            last = history[0]
            stats["last_backup"] = {
                "started_at": last.get("started_at").isoformat() if isinstance(last.get("started_at"), datetime) else last.get("started_at"),
                "status": last.get("status"),
                "success": last.get("status") == "completed"
            }
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de backup: {e}")
    
    # Calcular tamanho dos ficheiros locais
    try:
        if config.BACKUP_DIR.exists():
            for backup_file in config.BACKUP_DIR.glob("backup_*.zip"):
                stats["total_size_bytes"] += backup_file.stat().st_size
    except Exception as e:
        logger.error(f"Erro ao calcular tamanho dos backups: {e}")
    
    return stats


async def full_backup_workflow(upload_to_cloud: bool = True, cleanup_after: bool = True) -> dict:
    """
    Executa o workflow completo de backup: criação local, upload para S3 e
    limpeza de ficheiros antigos.

    Este é o workflow orquestrador chamado tanto pelo scheduler automático (03:00 UTC)
    como manualmente via endpoint de admin. A estratégia de "backup local primeiro"
    garante que existe sempre uma cópia recente, mesmo que o S3 esteja indisponível.

    Passos:
        1. Cria backup local (ZIP com JSON por coleção).
        2. Upload para S3 (opcional — falha silenciosamente sem comprometer o backup local).
        3. Remove backups locais com mais de BACKUP_LOCAL_RETENTION_DAYS dias.
        4. Remove backups S3 com mais de BACKUP_CLOUD_RETENTION_DAYS dias.

    Args:
        upload_to_cloud: Se True, faz upload do ZIP para o S3.
        cleanup_after: Se True, aplica políticas de retenção (local + cloud).

    Returns:
        dict: Resultado com chaves success, backup_path, size_bytes, uploaded,
            s3_url, cleaned_up e error.
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
    Job de backup agendado que corre diariamente às 03:00 UTC.

    O horário das 03:00 foi escolhido propositadamente: é fora do horário de
    expediente (minimiza interferência com operações), quando a carga no
    MongoDB de Produção é mais baixa, reduzindo o risco de lentidão
    noutras operações durante o dump da base de dados.

    Implementa proteção contra execuções concorrentes (_scheduled_backup_running)
    e regista cada execução na coleção backup_history para auditoria.
    """
    global _scheduled_backup_running
    
    if _scheduled_backup_running:
        logger.warning("Scheduled backup já está a correr, ignorando...")
        return
    
    _scheduled_backup_running = True
    
    try:
        from database import db
        import uuid
        
        logger.info("[SCHEDULED BACKUP] Iniciando backup automático...")
        
        # Criar ID único
        backup_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        
        # Registar início com ID único
        await db.backup_history.insert_one({
            "id": backup_id,
            "triggered_by": "system",
            "triggered_by_email": "scheduled",
            "trigger_type": "scheduled",
            "started_at": started_at,
            "status": "running"
        })
        
        # Executar backup
        result = await full_backup_workflow(
            upload_to_cloud=True,
            cleanup_after=True
        )
        
        # Actualizar registo com ID único
        await db.backup_history.update_one(
            {"id": backup_id},
            {"$set": {
                "status": "completed" if result["success"] else "failed",
                "result": result,
                "completed_at": datetime.now(timezone.utc)
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
    """Inicia o scheduler de backups automáticos como coroutine infinita.

    Calcula o próximo horário às 03:00 UTC e usa ``asyncio.sleep`` para
    esperar até essa hora. Após cada execução, agenda a próxima. Em caso de
    erro, espera 1 hora antes de tentar novamente (para evitar loops rápidos
    em caso de falha persistente).

    Esta função deve ser iniciada como background task no startup do servidor
    (``server.py``). O uso de ``asyncio.sleep`` em vez de cron/schedule é
    deliberado: evita dependências externas e funciona correctamente em
    ambientes serverless com warm pool.
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