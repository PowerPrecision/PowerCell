"""
Modelos de configuração de email por utilizador.
"""
from pydantic import BaseModel
from typing import Optional


class EmailConfigCreate(BaseModel):
    """Payload para configurar email do utilizador (POST).

    O campo password é opcional para permitir atualizar servidores
    sem ter de reenviar a password (a existente é mantida).
    """
    email_address: str
    password: Optional[str] = None  # Recebe em plain-text, será encriptada no endpoint
    imap_server: str
    imap_port: int = 993
    smtp_server: str
    smtp_port: int = 465


class EmailConfigResponse(BaseModel):
    """Resposta GET — nunca inclui a password real."""
    is_configured: bool
    email_address: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    has_password: bool = False


class EmailConfigTestResult(BaseModel):
    """Resultado do teste de ligação."""
    success: bool
    imap_connected: bool = False
    smtp_connected: bool = False
    error: Optional[str] = None
