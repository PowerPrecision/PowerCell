"""
====================================================================
ROTAS DE ADMINISTRAÇÃO - CONFIGURAÇÃO E MONITORIZAÇÃO DE IA
====================================================================
Extraído de admin.py para melhor organização.
Inclui: Configuração IA, Modelos, Tarefas, Cache, Usage Tracking.
====================================================================
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.auth import UserRole
from services.auth import require_roles


router = APIRouter(prefix="/admin", tags=["Admin - AI"])


# ============== AI CONFIGURATION ==============

@router.get("/ai-config")
async def get_ai_configuration(user: dict = Depends(require_roles([UserRole.ADMIN]))):
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
            "error_analysis": "Análise de erros de importação"
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
        "cache_settings": cache_settings
    }


# ============== AI MODELS CRUD ==============

@router.put("/ai-config")
async def update_ai_configuration(
    config: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Actualiza a configuração de IA."""
    from services.system_config import get_system_config, update_config_section
    
    # Actualizar na secção 'ai' do system_config
    try:
        await update_config_section("ai", config)
        
        return {
            "success": True,
            "message": "Configuração de IA actualizada com sucesso"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-models")
async def list_ai_models(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Lista todos os modelos de IA configurados."""
    from config import AI_MODELS
    
    db_models = await db.ai_models.find({}, {"_id": 0}).to_list(100)
    
    if db_models:
        return {"models": db_models, "source": "database"}
    
    models_list = [
        {"key": key, **value} 
        for key, value in AI_MODELS.items()
    ]
    return {"models": models_list, "source": "config"}


@router.post("/ai-models")
async def create_ai_model(
    key: str,
    name: str,
    provider: str,
    model_id: str,
    description: str = "",
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
    max_tokens: int = 4096,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Cria um novo modelo de IA."""
    existing = await db.ai_models.find_one({"key": key})
    if existing:
        raise HTTPException(status_code=400, detail=f"Modelo '{key}' já existe")
    
    model_doc = {
        "key": key,
        "name": name,
        "provider": provider,
        "model_id": model_id,
        "description": description,
        "cost_per_1k_input": cost_per_1k_input,
        "cost_per_1k_output": cost_per_1k_output,
        "max_tokens": max_tokens,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True
    }
    
    await db.ai_models.insert_one(model_doc)
    del model_doc["_id"]
    
    return {"success": True, "model": model_doc}


@router.put("/ai-models/{model_key}")
async def update_ai_model(
    model_key: str,
    name: str = None,
    description: str = None,
    cost_per_1k_input: float = None,
    cost_per_1k_output: float = None,
    is_active: bool = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Actualiza um modelo de IA."""
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if cost_per_1k_input is not None:
        update_data["cost_per_1k_input"] = cost_per_1k_input
    if cost_per_1k_output is not None:
        update_data["cost_per_1k_output"] = cost_per_1k_output
    if is_active is not None:
        update_data["is_active"] = is_active
    
    result = await db.ai_models.update_one({"key": model_key}, {"$set": update_data})
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    
    return {"success": True}


@router.delete("/ai-models/{model_key}")
async def delete_ai_model(
    model_key: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove um modelo de IA."""
    result = await db.ai_models.delete_one({"key": model_key})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    
    return {"success": True}


# ============== AI TASKS CRUD ==============

@router.get("/ai-tasks")
async def list_ai_tasks(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Lista todas as tarefas de IA configuradas."""
    db_tasks = await db.ai_tasks.find({}, {"_id": 0}).to_list(100)
    
    if db_tasks:
        return {"tasks": db_tasks, "source": "database"}
    
    default_tasks = [
        {"key": "scraper_extraction", "description": "Extração de dados de páginas web", "default_model": "gemini_flash"},
        {"key": "document_analysis", "description": "Análise de documentos", "default_model": "gpt4o_mini"},
        {"key": "weekly_report", "description": "Relatório semanal", "default_model": "gemini_flash"},
        {"key": "error_analysis", "description": "Análise de erros", "default_model": "gemini_flash"}
    ]
    return {"tasks": default_tasks, "source": "defaults"}


@router.post("/ai-tasks")
async def create_ai_task(
    key: str,
    description: str,
    default_model: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Cria uma nova tarefa de IA."""
    existing = await db.ai_tasks.find_one({"key": key})
    if existing:
        raise HTTPException(status_code=400, detail=f"Tarefa '{key}' já existe")
    
    task_doc = {
        "key": key,
        "description": description,
        "default_model": default_model,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.ai_tasks.insert_one(task_doc)
    del task_doc["_id"]
    
    return {"success": True, "task": task_doc}


@router.put("/ai-tasks/{task_key}")
async def update_ai_task(
    task_key: str,
    description: str = None,
    default_model: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
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


@router.delete("/ai-tasks/{task_key}")
async def delete_ai_task(
    task_key: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Remove uma tarefa de IA."""
    result = await db.ai_tasks.delete_one({"key": task_key})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    return {"success": True}


# ============== CACHE SETTINGS ==============

@router.get("/cache-settings")
async def get_cache_settings(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Obtém configurações de cache."""
    config = await db.system_config.find_one({"type": "cache_settings"}, {"_id": 0})
    return config or {"cache_limit": 1000, "notify_at_percentage": 80}


@router.put("/cache-settings")
async def update_cache_settings(
    cache_limit: int = None,
    notify_at_percentage: int = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Actualiza configurações de cache."""
    settings = {}
    if cache_limit is not None:
        settings["cache_limit"] = cache_limit
    if notify_at_percentage is not None:
        settings["notify_at_percentage"] = notify_at_percentage
    
    if not settings:
        raise HTTPException(status_code=400, detail="Nenhum campo para actualizar")
    
    settings["type"] = "cache_settings"
    settings["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.system_config.update_one(
        {"type": "cache_settings"},
        {"$set": settings},
        upsert=True
    )
    
    return {"success": True, "settings": settings}


# ============== AI USAGE TRACKING ==============

@router.get("/ai-usage/summary")
async def get_ai_usage_summary(
    period: str = "month",
    task: str = None,
    model: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém resumo de uso de IA."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_usage_summary(period, task, model)


@router.get("/ai-usage/by-task")
async def get_ai_usage_by_task(
    period: str = "month",
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém uso agregado por tarefa."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_usage_by_task(period)


@router.get("/ai-usage/by-model")
async def get_ai_usage_by_model(
    period: str = "month",
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém uso agregado por modelo."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_usage_by_model(period)


@router.get("/ai-usage/trend")
async def get_ai_usage_trend(
    days: int = 30,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém tendência diária de uso."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_daily_trend(days)


@router.get("/ai-usage/logs")
async def get_ai_usage_logs(
    limit: int = 50,
    task: str = None,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém logs recentes de chamadas à IA."""
    from services.ai_usage_tracker import ai_usage_tracker
    return await ai_usage_tracker.get_recent_logs(limit, task)


# ============== AI WEEKLY REPORT ==============

@router.get("/ai-report-recipients")
async def get_ai_report_recipients(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Obtém lista de destinatários do relatório semanal de IA."""
    config = await db.system_config.find_one({"type": "ai_report_config"}, {"_id": 0})
    
    if not config:
        return {"recipients": [], "enabled": False}
    
    return {
        "recipients": config.get("recipients", []),
        "enabled": config.get("enabled", False),
        "schedule": config.get("schedule", "monday_09:00")
    }


@router.post("/ai-report-recipients")
async def update_ai_report_recipients(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
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
                "updated_by": user["id"]
            }
        },
        upsert=True
    )
    
    return {"success": True, "recipients": recipients, "enabled": enabled}


@router.get("/ai-report-config")
async def get_ai_report_config(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Obtém configuração completa do relatório semanal de IA."""
    config = await db.system_config.find_one({"type": "ai_report_config"}, {"_id": 0})
    
    default_config = {
        "enabled": False,
        "recipients": [],
        "schedule": "monday_09:00",
        "include_usage_stats": True,
        "include_error_summary": True,
        "include_cost_breakdown": True
    }
    
    if config:
        default_config.update(config)
    
    return default_config


@router.put("/ai-report-config")
async def update_ai_report_config(
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Actualiza configuração do relatório semanal."""
    data["type"] = "ai_report_config"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user["id"]
    
    await db.system_config.update_one(
        {"type": "ai_report_config"},
        {"$set": data},
        upsert=True
    )
    
    return {"success": True}


@router.get("/ai-weekly-report")
async def get_current_ai_weekly_report(
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém o último relatório semanal de IA."""
    from services.ai_usage_tracker import ai_usage_tracker
    
    try:
        # Tentar obter o último relatório guardado
        last_report = await db.ai_weekly_reports.find_one(
            {},
            {"_id": 0},
            sort=[("generated_at", -1)]
        )
        
        if last_report:
            return {"success": True, "report": last_report}
        
        # Se não existir, gerar um novo
        usage_summary = await ai_usage_tracker.get_usage_summary("week")
        by_task = await ai_usage_tracker.get_usage_by_task("week")
        by_model = await ai_usage_tracker.get_usage_by_model("week")
        
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": "last_7_days",
            "usage_summary": usage_summary,
            "by_task": by_task,
            "by_model": by_model,
        }
        
        return {"success": True, "report": report}
        
    except Exception as e:
        return {"success": True, "report": None, "message": str(e)}


@router.post("/ai-weekly-report/generate")
async def generate_ai_weekly_report(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Gera relatório semanal de IA manualmente."""
    from services.ai_usage_tracker import ai_usage_tracker
    
    try:
        # Obter dados da última semana
        usage_summary = await ai_usage_tracker.get_usage_summary("week")
        by_task = await ai_usage_tracker.get_usage_by_task("week")
        by_model = await ai_usage_tracker.get_usage_by_model("week")
        
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": "last_7_days",
            "usage_summary": usage_summary,
            "by_task": by_task,
            "by_model": by_model,
        }
        
        # Guardar relatório
        report["id"] = str(uuid.uuid4())
        await db.ai_weekly_reports.insert_one(report)
        report.pop("_id", None)
        
        return {"success": True, "report": report}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/ai-weekly-report/history")
async def get_ai_weekly_report_history(
    limit: int = 10,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """Obtém histórico de relatórios semanais."""
    reports = await db.ai_weekly_reports.find(
        {},
        {"_id": 0}
    ).sort("generated_at", -1).limit(limit).to_list(limit)
    
    return {"reports": reports, "total": len(reports)}

