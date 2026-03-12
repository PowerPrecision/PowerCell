"""
=============================================================================
Rotas do Agente de Melhoria com IA
=============================================================================
Endpoints para análise preditiva e prescritiva de processos.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from services.auth import get_current_user
from services.ai_improvement_agent import ai_agent, run_weekly_analysis, analyze_process

router = APIRouter(prefix="/ai-agent", tags=["AI Agent"])


@router.get("/analyze")
async def analyze_all(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Executa análise completa de todos os processos ativos.
    Retorna estatísticas, alertas e sugestões.
    """
    # Apenas admin e CEO podem ver análise global
    if user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")
    
    result = await run_weekly_analysis()
    return result


@router.get("/analyze/{process_id}")
async def analyze_single(
    process_id: str,
    user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Análise detalhada de um processo específico.
    Inclui métricas, nível de risco e recomendações.
    """
    result = await analyze_process(process_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.get("/suggestions")
async def get_suggestions(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Obtém apenas as sugestões de melhoria.
    """
    result = await run_weekly_analysis()
    
    return {
        "suggestions": result.get("suggestions", []),
        "total_alerts": len(result.get("alerts", [])),
        "generated_at": result.get("generated_at")
    }


@router.get("/alerts")
async def get_alerts(
    severity: str = None,
    limit: int = 20,
    user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtém alertas de processos problemáticos.
    Pode filtrar por severidade: high, medium, low
    """
    result = await run_weekly_analysis()
    alerts = result.get("alerts", [])
    
    # Filtrar por severidade se especificado
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    
    return {
        "alerts": alerts[:limit],
        "total": len(alerts),
        "generated_at": result.get("generated_at")
    }


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Obtém estatísticas resumidas dos processos.
    """
    result = await run_weekly_analysis()
    
    return {
        "stats": result.get("stats", {}),
        "total_analyzed": result.get("total_analyzed", 0),
        "generated_at": result.get("generated_at")
    }
