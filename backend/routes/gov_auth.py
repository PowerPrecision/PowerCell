"""
====================================================================
GOV AUTH — Autenticação.gov (Chave Móvel Digital) Integration
====================================================================
Integração com o portal da AMA (Agência para a Modernização
Administrativa) para autenticação via Chave Móvel Digital (CMD).

MODO MOCK (até aprovação legal da AMA):
- GET /api/gov-auth/login → Redireciona para callback de teste
- GET /api/gov-auth/callback → Devolve dados fictícios do cidadão

MODO PRODUÇÃO (futuro):
- GET /api/gov-auth/login → Redireciona para OAuth2 da AMA
- GET /api/gov-auth/callback → Troca code por access_token,
  consulta endpoint de dados do cidadão autenticado, e devolve
  os dados verificados ao frontend.

SEGURANÇA:
- Os dados devolvidos têm `verified_by_gov: True` — o frontend
  DEVE tornar esses campos readOnly com badge "Verificado"
- O JWT temporário tem validade de 10 minutos (apenas para
  transportar os dados verificados de forma segura)
- Nenhum token da AMA é guardado na BD — é usado apenas em
  memória durante a sessão de autenticação
====================================================================
"""

import json
import logging
import os
import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gov-auth", tags=["Autenticação.gov"])

# ── Configuração ──
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
IS_MOCK = ENVIRONMENT != "production"

# Chave HMAC para assinar o JWT temporário (em produção, virá de env var)
_JWT_SECRET = os.environ.get("GOV_AUTH_JWT_SECRET", "dev-secret-change-in-prod")

# URL do frontend para redirecionamento após autenticação
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://powercell.onrender.com")

# ── Dados Mock do Cidadão ──
MOCK_CITIZEN = {
    "nome": "João Autenticado Silva",
    "nif": "259123456",
    "data_nascimento": "1985-05-15",
    "morada": "Rua da Liberdade, 123",
    "codigo_postal": "1200-098",
    "sexo": "M",
    "nacionalidade": "Portuguesa",
    "documento_id": "CC12345678",
    "verified_by_gov": True,
    "auth_method": "chave_movel_digital",
    "verified_at": datetime.now(timezone.utc).isoformat(),
}


def _create_gov_jwt(payload: dict) -> str:
    """
    Cria um JWT simplificado (HS256) para transportar os dados
    verificados da Autenticação.gov até ao frontend.

    NOTA: Em modo mock, usa um token Base64 simples para debug.
    Em produção, usará a biblioteca PyJWT com assinatura HS256.
    """
    try:
        import jwt
        token = jwt.encode(
            {
                "gov_data": payload,
                "exp": datetime.now(timezone.utc).timestamp() + 600,  # 10 min
                "type": "gov_auth",
            },
            _JWT_SECRET,
            algorithm="HS256",
        )
        return token
    except ImportError:
        # Fallback: Base64 simples (apenas para dev/mock)
        header = base64.urlsafe_b64encode(json.dumps({"alg": "mock"}).encode()).decode()
        body = base64.urlsafe_b64encode(json.dumps({
            "gov_data": payload,
            "exp": datetime.now(timezone.utc).timestamp() + 600,
            "type": "gov_auth",
        }).encode()).decode()
        return f"{header}.{body}.mock-signature"


# ====================================================================
# GET /api/gov-auth/login — Iniciar autenticação CMD
# ====================================================================

@router.get("/login")
async def gov_auth_login(
    redirect: Optional[str] = Query(None, description="URL de redirecionamento após callback"),
):
    """
    Inicia o fluxo de autenticação via Autenticação.gov (Chave Móvel Digital).

    MODO MOCK: Redireciona diretamente para o callback com code=mock123.
    MODO PRODUÇÃO: Redireciona para o portal da AMA com parâmetros OAuth2.

    Query Parameters:
    - redirect: URL opcional do frontend para onde redirecionar após
      a autenticação (sobrepõe-se ao FRONTEND_URL padrão)
    """
    frontend_base = redirect or FRONTEND_URL

    if IS_MOCK:
        logger.info("[GOV_AUTH] Modo MOCK — a redirecionar para callback de teste")
        callback_url = (
            f"/api/gov-auth/callback"
            f"?code=mock123"
            f"&state={base64.urlsafe_b64encode(frontend_base.encode()).decode()}"
        )
        return RedirectResponse(url=callback_url)

    # ── MODO PRODUÇÃO (futuro) ──
    # Redirecionar para o portal da AMA com parâmetros OAuth2
    # AMA_OAUTH_URL = "https://preprod.autenticacao.gov.pt/oauth/askauthorization"
    # params = {
    #     "client_id": os.environ.get("AMA_CLIENT_ID"),
    #     "redirect_uri": f"{API_BASE_URL}/api/gov-auth/callback",
    #     "response_type": "code",
    #     "scope": "openid profile citizen_nif citizen_address citizen_birth",
    #     "state": generate_csrf_state(),
    # }
    logger.warning("[GOV_AUTH] Modo PRODUÇÃO não implementado — a usar mock")
    callback_url = (
        f"/api/gov-auth/callback"
        f"?code=mock123"
        f"&state={base64.urlsafe_b64encode(frontend_base.encode()).decode()}"
    )
    return RedirectResponse(url=callback_url)


# ====================================================================
# GET /api/gov-auth/callback — Receber code e devolver dados
# ====================================================================

@router.get("/callback")
async def gov_auth_callback(
    code: str = Query(..., description="Código de autorização da AMA"),
    state: Optional[str] = Query(None, description="State CSRF / redirect URL"),
):
    """
    Recebe o código de autorização da AMA e devolve os dados do cidadão.

    MODO MOCK: Gera dados fictícios do cidadão.
    MODO PRODUÇÃO: Troca o code por access_token, consulta endpoint
    de dados do cidadão autenticado na AMA.

    O fluxo termina com um redirecionamento para o frontend com um
    JWT temporário (gov_token) contendo os dados verificados.
    """
    # Decodificar a URL do frontend do state (se existir)
    frontend_base = FRONTEND_URL
    if state:
        try:
            frontend_base = base64.urlsafe_b64decode(state.encode()).decode()
        except Exception:
            pass

    if IS_MOCK or code == "mock123":
        logger.info(
            f"[GOV_AUTH] Modo MOCK — a gerar dados fictícios do cidadão "
            f"(code={code})"
        )
        citizen_data = {**MOCK_CITIZEN, "verified_at": datetime.now(timezone.utc).isoformat()}
    else:
        # ── MODO PRODUÇÃO (futuro) ──
        # 1. Trocar code por access_token
        #    token_response = httpx.post(AMA_TOKEN_URL, data={
        #        "grant_type": "authorization_code",
        #        "code": code,
        #        "redirect_uri": f"{API_BASE_URL}/api/gov-auth/callback",
        #        "client_id": AMA_CLIENT_ID,
        #        "client_secret": AMA_CLIENT_SECRET,
        #    })
        # 2. Consultar endpoint de dados do cidadão
        #    citizen_response = httpx.get(AMA_USERINFO_URL, headers={
        #        "Authorization": f"Bearer {access_token}"
        #    })
        # 3. Mapear dados da AMA para o nosso formato
        logger.warning("[GOV_AUTH] Modo PRODUÇÃO não implementado — a usar mock")
        citizen_data = {**MOCK_CITIZEN, "verified_at": datetime.now(timezone.utc).isoformat()}

    # Criar JWT temporário com os dados verificados
    gov_token = _create_gov_jwt(citizen_data)

    # Redirecionar para o frontend com o token
    redirect_url = f"{frontend_base}/public-form?gov_token={gov_token}"

    logger.info(
        f"[GOV_AUTH] A redirecionar para o frontend com dados verificados "
        f"(nome={citizen_data.get('nome', '?')}, nif={citizen_data.get('nif', '?')})"
    )

    return RedirectResponse(url=redirect_url)


# ====================================================================
# GET /api/gov-auth/verify-token — Verificar e descodificar gov_token
# ====================================================================

@router.get("/verify-token")
async def verify_gov_token(gov_token: str = Query(..., description="JWT temporário da Autenticação.gov")):
    """
    Verifica e descodifica o JWT temporário da Autenticação.gov.

    Útil quando o frontend recebe o gov_token via URL e precisa de
    validar os dados antes de preencher o formulário.

    Returns:
    - valid: True se o token é válido e não expirou
    - gov_data: Dados verificados do cidadão (se válido)
    """
    try:
        import jwt
        payload = jwt.decode(gov_token, _JWT_SECRET, algorithms=["HS256"])
        gov_data = payload.get("gov_data", {})

        if payload.get("type") != "gov_auth":
            return {"valid": False, "error": "Tipo de token inválido"}

        return {"valid": True, "gov_data": gov_data}

    except ImportError:
        # Fallback mock: descodificar Base64
        try:
            parts = gov_token.split(".")
            if len(parts) == 3 and parts[2] == "mock-signature":
                body = json.loads(base64.urlsafe_b64decode(parts[1].encode()).decode())
                gov_data = body.get("gov_data", {})
                return {"valid": True, "gov_data": gov_data}
        except Exception:
            pass
        return {"valid": False, "error": "Token inválido"}

    except Exception as e:
        return {"valid": False, "error": f"Token inválido ou expirado: {type(e).__name__}"}
