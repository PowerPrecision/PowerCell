"""Health check for async jobs system.

Extraído de `routes/async_jobs.py`.
"""
from __future__ import annotations

import os

from services.async_jobs_api_models import ARQ_AVAILABLE


async def run_jobs_health_check():
    """Verificar saúde do sistema de jobs assíncronos."""
    return {
        "async_available": ARQ_AVAILABLE,
        "redis_configured": bool(os.environ.get("REDIS_URL")),
        "status": "healthy" if ARQ_AVAILABLE else "fallback_mode",
    }
