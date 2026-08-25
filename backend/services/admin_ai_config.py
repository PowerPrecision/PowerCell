"""Admin AI configuration + weekly report recipient/config handlers.

Extraído de `routes/admin_ai.py`. Prefer `admin_ai_config` / `admin_ai_*` —
do **not** create `services/admin_ai.py` (route module name) or overwrite
`admin_ai_data.py` (training/import logs from admin.py thinning).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from database import db


async def run_get_ai_configuration(user: dict) -> dict:
    """Obtém a configuração actual de IA."""
    from config import AI_MODELS, AI_CONFIG_DEFAULTS, GEMINI_API_KEY, EMERGENT_LLM_KEY
    from services.ai_page_analyzer import get_ai_config

    current_config = await get_ai_config()

    available_providers = []
    if GEMINI_API_KEY:
        available_providers.append("gemini")
    if EMERGENT_LLM_KEY:
        available_providers.append("openai")

    db_models = await db.ai_models.find({}, {"_id": 0}).to_list(100)
    if db_models:
        available_models = {m["key"]: m for m in db_models if m.get("provider") in available_providers}
    else:
        available_models = {}
        for model_key, model_info in AI_MODELS.items():
            if model_info["provider"] in available_providers:
                available_models[model_key] = model_info

    db_tasks = await db.ai_tasks.find({}, {"_id": 0}).to_list(100)
    if db_tasks:
        task_descriptions = {t["key"]: t["description"] for t in db_tasks}
        task_defaults = {t["key"]: t.get("default_model") for t in db_tasks}
    else:
        task_descriptions = {
            "scraper_extraction": "Extração de dados de páginas imobiliárias (scraping)",
            "document_analysis": "Análise e extração de dados de documentos",
            "weekly_report": "Geração do relatório semanal de erros",
            "error_analysis": "Análise de erros de importação",
        }
        task_defaults = AI_CONFIG_DEFAULTS

    cache_config = await db.system_config.find_one({"type": "cache_settings"}, {"_id": 0})
    cache_settings = cache_config or {"cache_limit": 1000, "notify_at_percentage": 80}

    return {
        "current_config": current_config,
        "defaults": task_defaults,
        "available_models": available_models,
        "available_providers": available_providers,
        "task_descriptions": task_descriptions,
        "cache_settings": cache_settings,
    }


async def run_update_ai_configuration(config: dict, user: dict) -> dict:
    """Actualiza a configuração de IA (mapeamento tarefa → modelo).

    NOTA: `run_get_ai_configuration` lê este mapeamento via `get_ai_config()`
    (services/ai_page_analyzer.py), que procura o documento
    `system_config` com `{"key": "ai_config"}`. Este endpoint tem de
    persistir exactamente nesse mesmo local — usar `update_config_section
    ("ai", ...)` (secção `SystemConfig.ai` com campos `provider`/`api_key`/
    `model`) escrevia noutro sítio e fazia o botão "Guardar" parecer que
    não persistia nada (o GET seguinte devolvia sempre os valores antigos).
    """
    try:
        await db.system_config.update_one(
            {"key": "ai_config"},
            {
                "$set": {
                    "key": "ai_config",
                    "value": config,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": user.get("id"),
                }
            },
            upsert=True,
        )
        return {
            "success": True,
            "message": "Configuração de IA actualizada com sucesso",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def run_get_ai_report_recipients(user: dict) -> dict:
    """Obtém lista de destinatários do relatório semanal de IA."""
    config = await db.system_config.find_one({"type": "ai_report_config"}, {"_id": 0})

    if not config:
        return {"recipients": [], "enabled": False}

    return {
        "recipients": config.get("recipients", []),
        "enabled": config.get("enabled", False),
        "schedule": config.get("schedule", "monday_09:00"),
    }


async def run_update_ai_report_recipients(data: dict, user: dict) -> dict:
    """Actualiza lista de destinatários do relatório semanal."""
    recipients = data.get("recipients", [])
    enabled = data.get("enabled", False)
    schedule = data.get("schedule", "monday_09:00")

    await db.system_config.update_one(
        {"type": "ai_report_config"},
        {
            "$set": {
                "type": "ai_report_config",
                "recipients": recipients,
                "enabled": enabled,
                "schedule": schedule,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": user["id"],
            }
        },
        upsert=True,
    )

    return {"success": True, "recipients": recipients, "enabled": enabled}


async def run_get_ai_report_config(user: dict) -> dict:
    """Obtém configuração completa do relatório semanal de IA."""
    config = await db.system_config.find_one({"type": "ai_report_config"}, {"_id": 0})

    default_config = {
        "enabled": False,
        "recipients": [],
        "schedule": "monday_09:00",
        "include_usage_stats": True,
        "include_error_summary": True,
        "include_cost_breakdown": True,
    }

    if config:
        default_config.update(config)

    return default_config


async def run_update_ai_report_config(data: dict, user: dict) -> dict:
    """Actualiza configuração do relatório semanal."""
    data["type"] = "ai_report_config"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user["id"]

    await db.system_config.update_one(
        {"type": "ai_report_config"},
        {"$set": data},
        upsert=True,
    )

    return {"success": True}
