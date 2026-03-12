import uuid
from datetime import datetime, timezone
from typing import Any

from database import db


async def log_history(process_id: str, user: dict, action: str, field: str = None, old_value: Any = None, new_value: Any = None):
    """Log a change to process history"""
    history_doc = {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "action": action,
        "field": field,
        "old_value": str(old_value) if old_value is not None else None,
        "new_value": str(new_value) if new_value is not None else None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.history.insert_one(history_doc)


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
