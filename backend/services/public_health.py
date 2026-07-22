"""Public health check.

Extraído de `routes/public.py`.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

async def run_public_health(request: Request):
    """Health check público."""
    return JSONResponse(status_code=200, content={"status": "ok", "public": True})

