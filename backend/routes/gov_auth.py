"""
====================================================================
GOV AUTH — Autenticação.gov (Chave Móvel Digital) — thin FastAPI stubs
====================================================================
Logic in services/gov_auth_api_*.py.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Query

from services.gov_auth_api_login import run_gov_auth_login
from services.gov_auth_api_callback import run_gov_auth_callback
from services.gov_auth_api_verify import run_verify_gov_token

router = APIRouter(prefix="/gov-auth", tags=["Autenticação.gov"])


@router.get("/login")
async def gov_auth_login(
    redirect: Optional[str] = Query(None, description="URL de redirecionamento após callback"),
):
    """Inicia o fluxo de autenticação via Autenticação.gov (Chave Móvel Digital)."""
    return await run_gov_auth_login(redirect)


@router.get("/callback")
async def gov_auth_callback(
    code: str = Query(..., description="Código de autorização da AMA"),
    state: Optional[str] = Query(None, description="State CSRF / redirect URL"),
):
    """Recebe o código de autorização da AMA e devolve os dados do cidadão."""
    return await run_gov_auth_callback(code, state)


@router.get("/verify-token")
async def verify_gov_token(gov_token: str = Query(..., description="JWT temporário da Autenticação.gov")):
    """Verifica e descodifica o JWT temporário da Autenticação.gov."""
    return await run_verify_gov_token(gov_token)
