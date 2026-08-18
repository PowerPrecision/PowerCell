"""Webmail público — thin stubs.

Download de anexos vive em ``services/email_mailbox_ops.py``.
Prefixo: ``/api/webmail`` (não colide com ``/api/emails/webmail``).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from services.auth import get_current_user
from services.email_mailbox_ops import run_download_webmail_attachment

router = APIRouter(prefix="/webmail", tags=["Webmail"])


@router.get("/attachments/{attachment_id}")
async def download_webmail_attachment(
    attachment_id: str,
    request: Request,
    email_id: Optional[str] = Query(None, description="ID do email pai (acelera a procura)"),
    current_user: dict = Depends(get_current_user),
):
    """Descarregar anexo de email como stream binário (Pacote DN.1)."""
    return await run_download_webmail_attachment(
        attachment_id, current_user, request, email_id=email_id
    )
