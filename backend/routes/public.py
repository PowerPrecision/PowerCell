"""
====================================================================
ROTAS PÚBLICAS - CREDITOIMO
====================================================================
Endpoints públicos (sem autenticação) — thin FastAPI stubs.

Logic in services/public_*.py.
Do **not** overwrite existing `services/euribor_service.py`.
Form defaults come from `routes.form_config` (re-export of form_config_defaults).

SEGURANÇA: Rate limiting preservado nos stubs.
====================================================================
"""
from fastapi import APIRouter, Request

from models.process import PublicClientRegistration
from middleware.rate_limit import limiter

from services.public_registration import run_public_client_registration
from services.public_health import run_public_health
from services.public_form_config import run_get_public_form_config
from services.public_euribor import run_get_euribor_rates

router = APIRouter(prefix="/public", tags=["Public"])


@router.post("/client-registration")
@limiter.limit("5/hour")  # Rate limit restritivo para prevenir spam de registos
async def public_client_registration(request: Request, data: PublicClientRegistration):
    return await run_public_client_registration(request, data)


@router.get("/health")
@limiter.limit("30/minute")
async def public_health(request: Request):
    return await run_public_health(request)


@router.get("/form-config")
@limiter.limit("60/minute")
async def get_public_form_config(request: Request):
    return await run_get_public_form_config(request)


@router.get("/euribor")
async def get_euribor_rates_endpoint():
    """
    Devolve as taxas Euribor reais (1M, 3M, 6M, 12M) com cache diário.
    Cache: 24h em memória (services/euribor_service.py).
    """
    return await run_get_euribor_rates()
