"""Shared helpers for Autenticação.gov handlers.

Extraído de `routes/gov_auth.py`.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

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
