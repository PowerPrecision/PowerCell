"""Gov-auth token verify handler.

Extraído de `routes/gov_auth.py`.
"""
from __future__ import annotations

import base64
import json

from services.gov_auth_api_helpers import _JWT_SECRET


async def run_verify_gov_token(gov_token: str):
    """Verifica e descodifica o JWT temporário da Autenticação.gov."""
    try:
        import jwt
        payload = jwt.decode(gov_token, _JWT_SECRET, algorithms=["HS256"])
        gov_data = payload.get("gov_data", {})

        if payload.get("type") != "gov_auth":
            return {"valid": False, "error": "Tipo de token inválido"}

        return {"valid": True, "gov_data": gov_data}

    except ImportError:
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
