"""Public Euribor rates endpoint wrapper.

Extraído de `routes/public.py`.
Do **not** overwrite existing `services/euribor_service.py` (cache/API core).
"""
from __future__ import annotations

from fastapi.responses import JSONResponse

from services.euribor_service import get_euribor_rates


async def run_get_euribor_rates():
    """Devolve as taxas Euribor reais (1M, 3M, 6M, 12M) com cache diário."""
    rates = await get_euribor_rates()
    return JSONResponse(status_code=200, content=rates)
