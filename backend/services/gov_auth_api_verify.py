"""Gov-auth token verify handler.

Extraído de `routes/gov_auth.py`.

O RAMO QUE ACEITAVA TOKENS POR ASSINAR (D-3, Set 2026)
=====================================================
Este verificador tinha um `except ImportError` que, se o `PyJWT` não
importasse, descodificava o token em Base64 e devolvia
`{"valid": True, ...}` desde que o terceiro segmento fosse o literal
`"mock-signature"` — ou seja, aceitava um `verified_by_gov: True`
escrito por qualquer pessoa.

Nunca correu (o `PyJWT==2.10.1` está fixado), mas a simetria com o
produtor tornava-o fácil de "reactivar por engano" num refactor. Saiu
dos DOIS lados no mesmo commit: manter só metade deixaria um produtor
sem consumidor ou — pior — um consumidor permissivo sem produtor, que é
a metade perigosa.
"""
from __future__ import annotations

from services.gov_auth_api_helpers import _JWT_SECRET


async def run_verify_gov_token(gov_token: str):
    """Verifica e descodifica o JWT temporário da Autenticação.gov."""
    import jwt

    try:
        payload = jwt.decode(gov_token, _JWT_SECRET, algorithms=["HS256"])
        gov_data = payload.get("gov_data", {})

        if payload.get("type") != "gov_auth":
            return {"valid": False, "error": "Tipo de token inválido"}

        return {"valid": True, "gov_data": gov_data}

    except Exception as e:
        return {"valid": False, "error": f"Token inválido ou expirado: {type(e).__name__}"}
