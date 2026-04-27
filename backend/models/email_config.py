"""
Modelos de configuração de email por utilizador.

Suporta dois modos de autenticação:
1. Clássico: IMAP/SMTP com password (qualquer provedor)
2. Google OAuth 2.0: via Gmail API (refresh_token encriptado)
"""
from pydantic import BaseModel
from typing import Optional


class EmailConfigCreate(BaseModel):
    """Payload para configurar email do utilizador (POST).

    O campo password é opcional para permitir atualizar servidores
    sem ter de reenviar a password (a existente é mantida).

    O campo google_refresh_token é preenchido automaticamente pelo
    fluxo OAuth 2.0 — não deve ser enviado manualmente pelo frontend.
    """
    email_address: str
    password: Optional[str] = None  # Recebe em plain-text, será encriptada no endpoint
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465
    google_refresh_token: Optional[str] = None  # Encriptado pelo OAuth callback


class EmailConfigResponse(BaseModel):
    """Resposta GET — nunca inclui a password real nem o refresh token real."""
    is_configured: bool
    email_address: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    has_password: bool = False
    has_google_oauth: bool = False  # Indica se tem refresh_token Google
    auth_method: str = "none"  # "none" | "imap_smtp" | "google_oauth"


class EmailConfigTestResult(BaseModel):
    """Resultado do teste de ligação."""
    success: bool
    imap_connected: bool = False
    smtp_connected: bool = False
    gmail_api_connected: bool = False  # True se testou via Gmail API
    auth_method: str = "imap_smtp"  # "imap_smtp" | "google_oauth"
    error: Optional[str] = None
