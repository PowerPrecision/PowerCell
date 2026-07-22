"""Shared helpers for internal chat.

Extraído de `routes/chat.py`.
"""
from __future__ import annotations

from fastapi import HTTPException


def block_parceiro(user: dict) -> None:
    """Bloqueia utilizadores com role 'parceiro' de enviar mensagens ou criar grupos."""
    if user.get("role") == "parceiro":
        raise HTTPException(
            status_code=403,
            detail="Apenas visualização disponível para parceiros. Não é possível enviar mensagens."
        )


# Alias matching original private name for call sites that prefer underscore form.
_block_parceiro = block_parceiro

# Tamanho máximo de anexo: 10MB
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = [
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv"
]
