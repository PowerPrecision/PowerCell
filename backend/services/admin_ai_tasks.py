"""Admin AI tasks CRUD handlers.

Extraído de `routes/admin_ai.py`. Prefer `admin_ai_tasks` / `admin_ai_*` —
do **not** create `services/admin_ai.py` or overwrite `admin_ai_data.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db


async def run_list_ai_tasks(user: dict) -> dict:
    """Lista todas as tarefas de IA configuradas."""
    db_tasks = await db.ai_tasks.find({}, {"_id": 0}).to_list(100)

    if db_tasks:
        return {"tasks": db_tasks, "source": "database"}

    default_tasks = [
        {"key": "scraper_extraction", "description": "Extração de dados de páginas web", "default_model": "gemini_flash"},
        {"key": "document_analysis", "description": "Análise de documentos", "default_model": "gpt4o_mini"},
        {"key": "weekly_report", "description": "Relatório semanal", "default_model": "gemini_flash"},
        {"key": "error_analysis", "description": "Análise de erros", "default_model": "gemini_flash"},
    ]
    return {"tasks": default_tasks, "source": "defaults"}


async def run_create_ai_task(
    key: str,
    description: str,
    default_model: str,
    user: Optional[dict] = None,
) -> dict:
    """Cria uma nova tarefa de IA."""
    existing = await db.ai_tasks.find_one({"key": key})
    if existing:
        raise HTTPException(status_code=400, detail=f"Tarefa '{key}' já existe")

    task_doc = {
        "key": key,
        "description": description,
        "default_model": default_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.ai_tasks.insert_one(task_doc)
    del task_doc["_id"]

    return {"success": True, "task": task_doc}


async def run_update_ai_task(
    task_key: str,
    description: Optional[str] = None,
    default_model: Optional[str] = None,
    user: Optional[dict] = None,
) -> dict:
    """Actualiza uma tarefa de IA."""
    update_data = {}
    if description is not None:
        update_data["description"] = description
    if default_model is not None:
        update_data["default_model"] = default_model

    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para actualizar")

    result = await db.ai_tasks.update_one({"key": task_key}, {"$set": update_data})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    return {"success": True}


async def run_delete_ai_task(task_key: str, user: Optional[dict] = None) -> dict:
    """Remove uma tarefa de IA."""
    result = await db.ai_tasks.delete_one({"key": task_key})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    return {"success": True}
