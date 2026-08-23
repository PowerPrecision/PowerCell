"""Backup ops — statistics, history, verify, config, status.

Extracted from `routes/backup.py`. Reuses `services.backup` core
(`get_backup_statistics`, `config`, `get_s3_client`). Does **not**
overwrite `services/backup.py`.
"""
from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.backup import config, get_backup_statistics, get_s3_client

logger = logging.getLogger(__name__)


async def run_get_statistics(user: dict) -> dict:
    """Obtém estatísticas dos backups (total, taxa sucesso, tamanho, último)."""
    stats = await get_backup_statistics()
    return {
        "success": True,
        "data": stats,
    }


async def run_get_history(user: dict, *, limit: int = 20) -> dict:
    """Obtém histórico de backups (mais recentes primeiro)."""
    history = await db.backup_history.find(
        {},
        {"_id": 0},
    ).sort("started_at", -1).limit(limit).to_list(limit)

    return {
        "success": True,
        "count": len(history),
        "history": history,
    }


async def run_verify_backups(user: dict) -> dict:
    """
    Verifica integridade dos backups.

    Verifica:
    - Último backup bem sucedido
    - Integridade dos ficheiros ZIP
    - Idade do último backup
    """
    stats = await get_backup_statistics()
    issues = []
    verified_files = []

    last_backup = stats.get("last_backup")
    if not last_backup:
        issues.append("Nenhum backup no histórico")
    elif not last_backup.get("success"):
        issues.append(f"Último backup falhou: {last_backup.get('error')}")

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

    for backup_file in config.BACKUP_DIR.glob("backup_*.zip"):
        try:
            with zipfile.ZipFile(backup_file, "r") as zf:
                test_result = zf.testzip()
                verified_files.append({
                    "filename": backup_file.name,
                    "size_mb": round(backup_file.stat().st_size / 1024 / 1024, 2),
                    "valid": test_result is None,
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
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_get_backup_config(user: dict) -> dict:
    """Obtém configuração actual do sistema de backup."""
    s3_configured = get_s3_client() is not None
    from services.backup import is_auto_backup_enabled

    auto_enabled = await is_auto_backup_enabled()

    return {
        "success": True,
        "config": {
            "backup_dir": str(config.BACKUP_DIR),
            "onedrive_folder": config.ONEDRIVE_BACKUP_FOLDER,
            "local_retention_days": config.LOCAL_RETENTION_DAYS,
            "cloud_retention_days": config.CLOUD_RETENTION_DAYS,
            "max_backup_size_mb": config.MAX_BACKUP_SIZE_MB,
            "s3_configured": s3_configured,
            "auto_backup_enabled": auto_enabled,
            "scheduled_backup": {
                "enabled": auto_enabled,
                "schedule": "03:00 UTC diariamente",
                "next_run": "Calculado automaticamente",
            },
        },
    }


async def run_get_backup_status(backup_id: str, user: dict) -> dict:
    """Obtém estado de um backup específico."""
    backup = await db.backup_history.find_one({"id": backup_id}, {"_id": 0})

    if not backup:
        raise HTTPException(status_code=404, detail="Backup não encontrado")

    return {
        "success": True,
        "backup": backup,
    }
