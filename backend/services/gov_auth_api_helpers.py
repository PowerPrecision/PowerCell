"""Shared helpers for Autenticação.gov handlers.

Extraído de `routes/gov_auth.py`.
"""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

# ── Configuração ──
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
IS_MOCK = ENVIRONMENT != "production"

# Chave HMAC para assinar o JWT temporário (em produção, virá de env var)
_JWT_SECRET = os.environ.get("GOV_AUTH_JWT_SECRET", "dev-secret-change-in-prod")

# URL do frontend para redirecionamento após autenticação
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://powercell.onrender.com")


def _is_allowed_redirect_origin(url: str) -> bool:
    """
    True se `url` for um endereço http(s) válido cuja origem pertence ao
    conjunto de domínios permitidos (as origens CORS configuradas).

    Mitigação de Open Redirect: sem isto, `?redirect=` (login) e `state`
    (callback) permitiam redirecionar o utilizador — e o `gov_token`
    entretanto emitido — para qualquer domínio arbitrário.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    origin = f"{parsed.scheme}://{parsed.netloc}"

    try:
        from config import CORS_ORIGINS, CORS_ORIGIN_REGEX
    except Exception:
        CORS_ORIGINS, CORS_ORIGIN_REGEX = [], []

    if origin in CORS_ORIGINS:
        return True

    for pattern in CORS_ORIGIN_REGEX:
        if re.match(pattern, origin):
            return True

    # Fallback: a própria FRONTEND_URL configurada é sempre permitida
    try:
        frontend_origin_parsed = urlparse(FRONTEND_URL)
        frontend_origin = f"{frontend_origin_parsed.scheme}://{frontend_origin_parsed.netloc}"
    except Exception:
        frontend_origin = FRONTEND_URL
    return origin == frontend_origin


def resolve_safe_redirect_base(redirect: Optional[str]) -> str:
    """
    Devolve `redirect` apenas se pertencer a um domínio permitido; caso
    contrário devolve `FRONTEND_URL` por defeito (mitigação Open Redirect).
    """
    if redirect and _is_allowed_redirect_origin(redirect):
        return redirect
    return FRONTEND_URL


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


def create_gov_jwt(payload: dict) -> str:
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
