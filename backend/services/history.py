import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from database import db

logger = logging.getLogger(__name__)


async def log_history(process_id: str, user: dict, action: str, field: str = None, old_value: Any = None, new_value: Any = None):
    """Log a change to process history"""
    # ================================================================
    # INDEXAÇÃO - MODO FANTASMA (SEM HISTÓRICO)
    # Utilizadores com role "indexacao" não registam ações no histórico
    # Isto permite que possam trabalhar nos processos sem deixar rasto
    # ================================================================
    if user and user.get("role") == "indexacao":
        logger.debug(f"[HISTORY] Modo fantasma: ignorando registo para indexacao - {action}")
        return
    
    try:
        history_doc = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "user_id": user.get("id") if user else None,
            "user_name": user.get("name") if user else "Sistema",
            "action": action,
            "field": field,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.history.insert_one(history_doc)
    except Exception as e:
        # Não falhar o upload se o histórico falhar
        import logging
        logging.getLogger(__name__).warning(f"Erro ao registar histórico: {e}")


async def log_data_changes(process_id: str, user: dict, old_data: dict, new_data: dict, section: str):
    """Compare and log changes between old and new data"""
    if old_data is None:
        old_data = {}
    if new_data is None:
        return
    
    for key, new_val in new_data.items():
        old_val = old_data.get(key)
        if old_val != new_val and new_val is not None:
            await log_history(
                process_id, user, 
                f"Alterou {section}", 
                key, old_val, new_val
            )
