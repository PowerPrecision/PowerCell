"""
====================================================================
AI USAGE TRACKER - CREDITOIMO
====================================================================
Sistema de tracking de uso de IA para acompanhar custos por tarefa,
modelo e período.

Colecções:
- ai_usage_logs: Regista cada chamada à IA
- ai_usage_summary: Resumos diários/mensais

Métricas rastreadas:
- Número de chamadas por tarefa/modelo
- Tokens consumidos (input + output)
- Custo estimado em EUR
- Tempo de resposta médio
====================================================================
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class AIUsageTracker:
    """Tracker de uso de IA."""
    
    def __init__(self):
        self._db = None
    
    async def _get_db(self):
        """Lazy load database connection."""
        if self._db is None:
            from database import db
            self._db = db
        return self._db
    
    async def log_usage(
        self,
        task: str,
        model: str,
        provider: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
        response_time_ms: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Regista uma utilização de IA.
        
        Args:
            task: Nome da tarefa (scraper_extraction, document_analysis, etc.)
            model: Modelo utilizado (gemini-2.0-flash, gpt-4o-mini, etc.)
            provider: Provider (gemini, openai, anthropic)
            input_tokens: Número de tokens de entrada
            output_tokens: Número de tokens de saída
            cost: Custo estimado em EUR
            response_time_ms: Tempo de resposta em milissegundos
            success: Se a chamada foi bem-sucedida
            error_message: Mensagem de erro (se aplicável)
            metadata: Dados adicionais
            
        Returns:
            ID do registo criado
        """
        db = await self._get_db()
        
        now = datetime.now(timezone.utc)
        
        log_entry = {
            "id": f"ai_{now.strftime('%Y%m%d%H%M%S%f')}",
            "task": task,
            "model": model,
            "provider": provider,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_eur": cost,
            "response_time_ms": response_time_ms,
            "success": success,
            "error_message": error_message,
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "month": now.strftime("%Y-%m")
        }
        
        try:
            await db.ai_usage_logs.insert_one(log_entry)
            
            # Actualizar resumo diário
            await self._update_daily_summary(task, model, provider, log_entry, now)
            
            logger.debug(f"AI usage logged: {task}/{model} - {input_tokens + output_tokens} tokens, €{cost:.6f}")
            
            return log_entry["id"]
            
        except Exception as e:
            logger.error(f"Erro ao registar uso de IA: {e}")
            return ""
    
    async def _update_daily_summary(
        self,
        task: str,
        model: str,
        provider: str,
        log_entry: Dict[str, Any],
        now: datetime
    ):
        """Actualiza o resumo diário de uso."""
        db = await self._get_db()
        
        date_str = now.strftime("%Y-%m-%d")
        summary_id = f"daily_{date_str}_{task}_{model}"
        
        await db.ai_usage_summary.update_one(
            {"summary_id": summary_id},
            {
                "$inc": {
                    "call_count": 1,
                    "success_count": 1 if log_entry["success"] else 0,
                    "error_count": 0 if log_entry["success"] else 1,
                    "total_input_tokens": log_entry["input_tokens"],
                    "total_output_tokens": log_entry["output_tokens"],
                    "total_tokens": log_entry["total_tokens"],
                    "total_cost_eur": log_entry["cost_eur"],
                    "total_response_time_ms": log_entry["response_time_ms"]
                },
                "$set": {
                    "task": task,
                    "model": model,
                    "provider": provider,
                    "date": date_str,
                    "month": now.strftime("%Y-%m"),
                    "type": "daily",
                    "updated_at": now.isoformat()
                },
                "$setOnInsert": {
                    "created_at": now.isoformat()
                }
            },
            upsert=True
        )
    
    async def get_usage_summary(
        self,
        period: str = "today",
        task: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtém resumo de uso de IA.
        
        Args:
            period: "today", "week", "month", "all"
            task: Filtrar por tarefa específica
            model: Filtrar por modelo específico
            
        Returns:
            Resumo com métricas agregadas
        """
        db = await self._get_db()
        
        # Definir filtro de data
        now = datetime.now(timezone.utc)
        date_filter = {}
        
        if period == "today":
            date_filter["date"] = now.strftime("%Y-%m-%d")
        elif period == "week":
            week_ago = now - timedelta(days=7)
            date_filter["date"] = {"$gte": week_ago.strftime("%Y-%m-%d")}
        elif period == "month":
            date_filter["month"] = now.strftime("%Y-%m")
        # "all" não tem filtro de data
        
        # Adicionar filtros opcionais
        query = {**date_filter, "type": "daily"}
        if task:
            query["task"] = task
        if model:
            query["model"] = model
        
        # Agregar dados
        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total_calls": {"$sum": "$call_count"},
                    "total_success": {"$sum": "$success_count"},
                    "total_errors": {"$sum": "$error_count"},
                    "total_input_tokens": {"$sum": "$total_input_tokens"},
                    "total_output_tokens": {"$sum": "$total_output_tokens"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_cost_eur": {"$sum": "$total_cost_eur"},
                    "avg_response_time_ms": {"$avg": "$total_response_time_ms"}
                }
            }
        ]
        
        result = await db.ai_usage_summary.aggregate(pipeline).to_list(1)
        
        if result:
            summary = result[0]
            del summary["_id"]
            summary["period"] = period
            summary["success_rate"] = (
                (summary["total_success"] / summary["total_calls"] * 100)
                if summary["total_calls"] > 0 else 0
            )
            return summary
        
        return {
            "period": period,
            "total_calls": 0,
            "total_success": 0,
            "total_errors": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_eur": 0.0,
            "avg_response_time_ms": 0,
            "success_rate": 0
        }
    
    async def get_usage_by_task(self, period: str = "month") -> List[Dict[str, Any]]:
        """Obtém uso agregado por tarefa."""
        db = await self._get_db()
        
        now = datetime.now(timezone.utc)
        date_filter = {}
        
        if period == "today":
            date_filter["date"] = now.strftime("%Y-%m-%d")
        elif period == "week":
            week_ago = now - timedelta(days=7)
            date_filter["date"] = {"$gte": week_ago.strftime("%Y-%m-%d")}
        elif period == "month":
            date_filter["month"] = now.strftime("%Y-%m")
        
        pipeline = [
            {"$match": {**date_filter, "type": "daily"}},
            {
                "$group": {
                    "_id": "$task",
                    "total_calls": {"$sum": "$call_count"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_cost_eur": {"$sum": "$total_cost_eur"},
                    "success_rate": {
                        "$avg": {
                            "$cond": [
                                {"$eq": ["$call_count", 0]},
                                0,
                                {"$divide": ["$success_count", "$call_count"]}
                            ]
                        }
                    }
                }
            },
            {"$sort": {"total_cost_eur": -1}}
        ]
        
        results = await db.ai_usage_summary.aggregate(pipeline).to_list(100)
        
        return [
            {
                "task": r["_id"],
                "total_calls": r["total_calls"],
                "total_tokens": r["total_tokens"],
                "total_cost_eur": round(r["total_cost_eur"], 6),
                "success_rate": round(r["success_rate"] * 100, 1)
            }
            for r in results
        ]
    
    async def get_usage_by_model(self, period: str = "month") -> List[Dict[str, Any]]:
        """Obtém uso agregado por modelo."""
        db = await self._get_db()
        
        now = datetime.now(timezone.utc)
        date_filter = {}
        
        if period == "today":
            date_filter["date"] = now.strftime("%Y-%m-%d")
        elif period == "week":
            week_ago = now - timedelta(days=7)
            date_filter["date"] = {"$gte": week_ago.strftime("%Y-%m-%d")}
        elif period == "month":
            date_filter["month"] = now.strftime("%Y-%m")
        
        pipeline = [
            {"$match": {**date_filter, "type": "daily"}},
            {
                "$group": {
                    "_id": {"model": "$model", "provider": "$provider"},
                    "total_calls": {"$sum": "$call_count"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_cost_eur": {"$sum": "$total_cost_eur"}
                }
            },
            {"$sort": {"total_cost_eur": -1}}
        ]
        
        results = await db.ai_usage_summary.aggregate(pipeline).to_list(100)
        
        return [
            {
                "model": r["_id"]["model"],
                "provider": r["_id"]["provider"],
                "total_calls": r["total_calls"],
                "total_tokens": r["total_tokens"],
                "total_cost_eur": round(r["total_cost_eur"], 6)
            }
            for r in results
        ]
    
    async def get_daily_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Obtém tendência diária de uso."""
        db = await self._get_db()
        
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        
        pipeline = [
            {"$match": {"type": "daily", "date": {"$gte": start_date}}},
            {
                "$group": {
                    "_id": "$date",
                    "total_calls": {"$sum": "$call_count"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "total_cost_eur": {"$sum": "$total_cost_eur"}
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        results = await db.ai_usage_summary.aggregate(pipeline).to_list(100)
        
        return [
            {
                "date": r["_id"],
                "total_calls": r["total_calls"],
                "total_tokens": r["total_tokens"],
                "total_cost_eur": round(r["total_cost_eur"], 6)
            }
            for r in results
        ]
    
    async def get_recent_logs(self, limit: int = 50, task: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtém logs recentes de uso de IA."""
        db = await self._get_db()
        
        query = {}
        if task:
            query["task"] = task
        
        logs = await db.ai_usage_logs.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        return logs


# Instância global
ai_usage_tracker = AIUsageTracker()


# Função helper para calcular custo estimado
def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estima o custo de uma chamada à IA.
    
    Preços aproximados (EUR) por 1M tokens:
    - Gemini 2.0 Flash: €0.10 input, €0.30 output
    - GPT-4o Mini: €0.15 input, €0.60 output
    - GPT-4o: €2.50 input, €10.00 output
    """
    PRICING = {
        "gemini-2.0-flash": {"input": 0.10 / 1_000_000, "output": 0.30 / 1_000_000},
        "gemini-1.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
        "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
        "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    }
    
    prices = PRICING.get(model, {"input": 0.001 / 1_000_000, "output": 0.002 / 1_000_000})
    
    return (input_tokens * prices["input"]) + (output_tokens * prices["output"])
