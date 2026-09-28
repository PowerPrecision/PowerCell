"""Shared helpers for Autenticação.gov handlers.

Extraído de `routes/gov_auth.py`.
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

# ── Configuração ──
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
IS_MOCK = ENVIRONMENT != "production"

#: Ambientes em que um segredo em falta é FATAL. Alinhado com o
#: `config.py`, que é quem já decide isto para o `JWT_SECRET`.
AMBIENTES_DE_PRODUCAO = ("production", "prod")

#: O literal que aqui viveu até Set 2026 — `"dev-secret-change-in-prod"`.
#: Fica registado no teste, não no código: uma guarda de fonte afirma que
#: nenhuma variação dele volta a aparecer neste módulo.


def _resolver_segredo(ambiente: str, valor: Optional[str]) -> str:
    """O segredo HMAC do `gov_token`, ou morte no arranque. PURO.

    PORQUE É QUE NÃO HÁ VALOR POR OMISSÃO (D-3, Set 2026)
    =====================================================
    Este módulo tinha
    `os.environ.get("GOV_AUTH_JWT_SECRET", "dev-secret-change-in-prod")`,
    e a variável **não estava declarada no `render.yaml`** — ou seja,
    produção assinava com um literal público. O `gov_token` carrega
    `verified_by_gov: True` e pré-preenche o formulário público: com o
    segredo conhecido, qualquer pessoa forjava uma identidade
    "verificada pelo Estado".

    É o mesmo padrão do CORS do bucket S3 e dos sourcemaps: **um recurso
    em código que ninguém vê falhar**. Um valor por omissão transforma
    "esqueceram-se de configurar" — que daria erro e seria corrigido em
    cinco minutos — em "está a funcionar, e mal", que dura meses.

    Em produção sem variável: `sys.exit(1)`, o padrão que o `config.py`
    já usa para o `JWT_SECRET` e o `CORS_ORIGINS`.

    Fora de produção sem variável: um segredo **aleatório por processo**,
    e não um literal. Um literal partilhado é um segredo conhecido em
    qualquer máquina que corra o código; aleatório, os tokens não
    sobrevivem a um reinício — que é exactamente o que se quer de um
    token com 10 minutos de vida num ambiente de desenvolvimento.
    """
    if valor:
        return valor

    if (ambiente or "").strip().lower() in AMBIENTES_DE_PRODUCAO:
        print(
            "❌ ERRO FATAL: Variável de ambiente 'GOV_AUTH_JWT_SECRET' não definida!",
            file=sys.stderr,
        )
        print(
            "   O gov_token declara `verified_by_gov` e pré-preenche o "
            "formulário público — sem segredo próprio é forjável.",
            file=sys.stderr,
        )
        print("   Gere um secret seguro: openssl rand -hex 32", file=sys.stderr)
        sys.exit(1)

    efemero = secrets.token_hex(32)
    print(
        "⚠️  AVISO (DEV): GOV_AUTH_JWT_SECRET não definida — a usar um "
        "segredo aleatório desta instância.",
        file=sys.stderr,
    )
    print(
        "   Os gov_token não sobrevivem a um reinício. Em PRODUÇÃO isto "
        "seria bloqueado.",
        file=sys.stderr,
    )
    return efemero


_JWT_SECRET = _resolver_segredo(ENVIRONMENT, os.environ.get("GOV_AUTH_JWT_SECRET"))

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
    Cria um JWT (HS256) para transportar os dados verificados da
    Autenticação.gov até ao frontend.

    NÃO HÁ RECURSO SEM ASSINATURA (D-3, Set 2026)
    =============================================
    Esta função tinha um `except ImportError` que devolvia um token
    Base64 terminado no literal `"mock-signature"`, e o verificador
    tinha o ramo simétrico que o ACEITAVA sem verificar assinatura
    nenhuma — um `verified_by_gov: True` para quem soubesse escrever
    três segmentos separados por pontos.

    Nunca foi explorável: o `PyJWT==2.10.1` está fixado no
    `requirements.txt`, logo o `import jwt` nunca falhou e o ramo nunca
    correu. Foi removido à mesma, porque **código adormecido atrás de
    uma condição que hoje é falsa é um convite a religá-lo** — e aqui o
    que se religaria era a aceitação de tokens por assinar.

    Um `ImportError` do PyJWT hoje não é um caso a degradar: é a
    aplicação inteira sem autenticação, e deve rebentar.
    """
    import jwt

    return jwt.encode(
        {
            "gov_data": payload,
            "exp": datetime.now(timezone.utc).timestamp() + 600,  # 10 min
            "type": "gov_auth",
        },
        _JWT_SECRET,
        algorithm="HS256",
    )
