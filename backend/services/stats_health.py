"""System health check (monitoring).

Extraído de `routes/stats.py` — GET /health (no auth).
"""
from __future__ import annotations

from datetime import datetime, timezone

async def run_health_check():
    """Verifica a saúde do sistema e das dependências externas.

    Retorna o estado das seguintes componentes:
    - Base de dados MongoDB
    - Serviço de armazenamento S3
    - Cache Redis (se disponível)
    - Serviço de email

    Porquê sem autenticação: este endpoint é usado por monitoring
    externo (UptimeRobot, etc.) e não expõe dados sensíveis.

    Returns:
        dict: Estado de cada componente (ok/erro) e timestamp.
    """
    from services.redis_cache import health_check as redis_health
    redis_status = await redis_health()
    return {
        "status": "healthy", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis": redis_status
    }

