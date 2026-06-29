"""
====================================================================
ROTAS DE ADMIN DO PORTAL DO CLIENTE — IMPERSONATION
====================================================================
Endpoints internos (staff) para gestão do Portal do Cliente que
NÃO estão no router público do portal (`portal.py`).

Atualmente expõe apenas a funcionalidade de "Ver como Cliente"
(impersonation) — permite a um consultor/intermediário/diretor/admin
abrir o Portal do Cliente de um processo num novo separador,
autenticado automaticamente, para prestar suporte ao cliente.

SEGURANÇA:
- Todos os endpoints exigem `require_staff()` (qualquer perfil interno).
- O token gerado é um JWT normal do Portal (role=client_portal,
  type=magic_link), pelo que o frontend do portal aceita-o sem
  alterações. A diferenciação entre um magic link "real" e um
  impersonate é feita pelos metadados no documento `portal_tokens`
  (`impersonated_by`, `impersonated_by_email`) e por registos no
  `audit_trail` + `history`.
- O log de segurança segue o formato pedido:
    "O utilizador X assumiu a identidade do cliente no processo Y"

Autor: PowerCell Development Team
====================================================================
"""
import os
import secrets
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from services.auth import require_staff
from services.portal_security import (
    create_client_magic_token,
    PORTAL_TOKEN_VALIDITY_DAYS,
)
from services.history import log_history
from services.audit_trail_service import log_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Portal Admin (Impersonation)"])


def _get_frontend_url(request: Request) -> str:
    """
    Obtém a URL base do frontend (igual ao helper em processes.py).

    Prioridade:
    1. Header Referer/Origin (vem do browser do staff)
    2. Env var FRONTEND_URL
    3. String vazia (o chamador decide o que fazer)
    """
    referer = request.headers.get("referer") or request.headers.get("origin")
    if referer:
        from urllib.parse import urlparse
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    frontend_url = os.environ.get("FRONTEND_URL")
    if frontend_url:
        return frontend_url.rstrip("/")

    logger.warning(
        "[IMPERSONATE] FRONTEND_URL não configurada e sem Referer header. "
        "O URL devolvido ficará incompleto — configure a env var FRONTEND_URL."
    )
    return ""


@router.post("/impersonate/{process_id}")
async def impersonate_client_portal(
    process_id: str,
    request: Request,
    user: dict = Depends(require_staff()),
):
    """
    Gera um link do Portal do Cliente autenticado para um membro do staff
    "ver como cliente" (impersonation).

    Fluxo:
    1. Verificar que o processo existe (sem filtrar is_deleted, para
       distinguir "não encontrado" de "eliminado" — alinhado com o
       comportamento do GET /processes/{id}).
    2. Recusar processos eliminados (o Portal recusa acessos a
       eliminados — não faz sentido gerar um link inútil).
    3. Gerar JWT magic_link (idêntico ao do Portal do Cliente) via
       `create_client_magic_token`.
    4. Gerar short_id (8 chars URL-safe) e guardar em `portal_tokens`
       com metadados `impersonated_by` + `impersonated_by_email` para
       auditoria.
    5. Registar no `audit_trail` (com metadata.impersonate=True) e
       no `history` do processo, com a mensagem:
       "O utilizador {email} assumiu a identidade do cliente no
       processo {process_id}".
    6. Devolver `{"url": "...", "short_id": "...", "process_id": "...",
       "client_name": "...", "expires_in_days": 90}`.

    O URL tem o formato `{FRONTEND_URL}/portal/{short_id}` — o mesmo
    que o magic link normal, pelo que o frontend do portal abre sem
    alterações.

    Returns:
        dict com `url` (pronto a clicar) + metadados.

    Raises:
        HTTPException(404): Processo não encontrado.
        HTTPException(404): Processo eliminado (com mensagem acionável).
    """
    # 1. Lookup do processo (sem filtro is_deleted — ver docstring)
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # 2. Recusar eliminados
    if process.get("is_deleted"):
        raise HTTPException(
            status_code=404,
            detail="Este processo foi eliminado. Restaure-o antes de usar Ver como Cliente."
        )

    client_name = process.get("client_name", "Cliente")
    client_email = process.get("client_email", "")
    client_id = process.get("client_id", "")

    # 3. Gerar JWT idêntico ao do Portal do Cliente
    token = create_client_magic_token(process_id)

    # 4. Gerar short_id e guardar em portal_tokens COM metadados de impersonate
    short_id = secrets.token_urlsafe(6)[:8]
    now = datetime.now(timezone.utc)

    await db.portal_tokens.update_one(
        {"process_id": process_id, "impersonated_by": user.get("id")},
        {
            "$set": {
                "short_id": short_id,
                "jwt_token": token,
                "process_id": process_id,
                "client_id": client_id,
                "created_by": user.get("email", ""),
                # Metadados de impersonate (permitem distinguir de magic
                # links "reais" nas queries de auditoria)
                "impersonated_by": user.get("id"),
                "impersonated_by_email": user.get("email"),
                "impersonated_by_name": user.get("name"),
                "impersonated_by_role": user.get("role"),
                "impersonated_at": now,
                "token_type": "staff_impersonate",
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    # 5. Construir URL (mesmo formato do magic link)
    frontend_url = _get_frontend_url(request)
    impersonate_url = f"{frontend_url}/portal/{short_id}"

    # 6. Logs de segurança (audit_trail + history + logger)
    audit_msg = (
        f"O utilizador {user.get('email')} assumiu a identidade do "
        f"cliente no processo {process_id}"
    )
    logger.info(f"[IMPERSONATE] {audit_msg} (cliente: {client_name})")

    try:
        await log_audit_event(
            process_id=process_id,
            user=user,
            action="Impersonate — Ver como Cliente no Portal",
            field="portal_impersonate",
            new_value=short_id,
            request=request,
            source="web",
            audit_reason="Suporte ao cliente (ver portal como cliente)",
            metadata={
                "impersonate": True,
                "impersonated_by_email": user.get("email"),
                "impersonated_by_role": user.get("role"),
                "short_id": short_id,
                "client_id": client_id,
                "client_name": client_name,
            },
        )
    except Exception as e:
        logger.warning(f"[IMPERSONATE] Não foi possível registar audit_trail: {e}")

    try:
        await log_history(
            process_id=process_id,
            user=user,
            action=(
                f"Impersonate — {user.get('name', 'Staff')} assumiu a "
                f"identidade do cliente no Portal (suporte)"
            ),
            field="portal_impersonate",
            new_value=short_id,
        )
    except Exception as e:
        logger.warning(f"[IMPERSONATE] Não foi possível registar history: {e}")

    # 7. Resposta
    return {
        "url": impersonate_url,
        "short_id": short_id,
        "process_id": process_id,
        "client_name": client_name,
        "client_email": client_email,
        "expires_in_days": PORTAL_TOKEN_VALIDITY_DAYS,
        "impersonated_by": user.get("email"),
        "impersonated_by_name": user.get("name"),
    }
