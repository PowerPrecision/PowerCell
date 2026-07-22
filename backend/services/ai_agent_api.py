"""
AI Agent API handlers — analyze / suggestions / alerts / stats.

Extraído de `routes/ai_agent.py`.
Do **not** overwrite `services/ai_improvement_agent.py` (core agent).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from services.ai_improvement_agent import analyze_process, run_weekly_analysis


async def run_analyze_all(user: dict) -> Dict[str, Any]:
    """Executa análise completa de todos os processos ativos."""
    if user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")

    return await run_weekly_analysis()


async def run_analyze_single(process_id: str) -> Dict[str, Any]:
    """Análise detalhada de um processo específico."""
    result = await analyze_process(process_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


async def run_get_suggestions() -> Dict[str, Any]:
    """Obtém apenas as sugestões de melhoria."""
    result = await run_weekly_analysis()

    return {
        "suggestions": result.get("suggestions", []),
        "total_alerts": len(result.get("alerts", [])),
        "generated_at": result.get("generated_at"),
    }


async def run_get_alerts(
    severity: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Obtém alertas de processos problemáticos."""
    result = await run_weekly_analysis()
    alerts = result.get("alerts", [])

    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]

    return {
        "alerts": alerts[:limit],
        "total": len(alerts),
        "generated_at": result.get("generated_at"),
    }


async def run_get_stats() -> Dict[str, Any]:
    """Obtém estatísticas resumidas dos processos."""
    result = await run_weekly_analysis()

    return {
        "stats": result.get("stats", {}),
        "total_analyzed": result.get("total_analyzed", 0),
        "generated_at": result.get("generated_at"),
    }
