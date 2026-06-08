"""
====================================================================
MODELO: EmailConfig — Configuração de Email por Utilizador e Empresa
====================================================================

Suporta dois modos de autenticação:
1. Clássico: IMAP/SMTP com password (qualquer provedor)
2. Google OAuth 2.0: via Gmail API (refresh_token encriptado)

MULTI-EMPRESA:
  O campo company_id é uma CHAVE ESTRANGEIRA que associa a configuração
  de email a uma empresa específica. A restrição de unicidade é a
  combinação (user_id, company_id) — um utilizador só pode ter UMA
  config de email por empresa.

COLEÇÃO MONGODB: user_email_configs
INDEX: { user_id: 1, company_id: 1 } (unique composto)

BACKWARD COMPATIBILITY:
  A config também é guardada embebida no user.email_config (nested dict)
  sob a chave "company:<company_id>" para retrocompatibilidade com código
  que ainda lê daí. A coleção user_email_configs é a fonte canónica.

CAMPOS DA COLEÇÃO:
  - id: UUID (PK)
  - user_id: FK para db.users.id
  - company_id: FK para db.company_email_configs.company_name (ou string)
  - email_address: Endereço de email do utilizador
  - imap_server, imap_port, smtp_server, smtp_port: Servidores
  - encrypted_password: Password encriptada (Fernet)
  - google_refresh_token, google_access_token, google_email: OAuth
  - auth_method: "none" | "imap_smtp" | "google_oauth"
  - oauth_connected_at: Timestamp da ligação OAuth
  - is_configured: Se a config está completa
  - created_at / updated_at: Timestamps
====================================================================
"""
from pydantic import BaseModel, field_validator
from typing import Optional, List


class EmailConfigCreate(BaseModel):
    """Payload para configurar email do utilizador (POST).

    O campo password é opcional para permitir atualizar servidores
    sem ter de reenviar a password (a existente é mantida).

    O campo google_refresh_token é preenchido automaticamente pelo
    fluxo OAuth 2.0 — não deve ser enviado manualmente pelo frontend.

    O campo company_id identifica a empresa a que esta config pertence.
    É OBRIGATÓRIO — se não for fornecido, usa "default" (retrocompat).
    A unicidade é garantida pela combinação (user_id, company_id).
    """
    email_address: str
    password: Optional[str] = None  # Recebe em plain-text, será encriptada no endpoint
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465
    google_refresh_token: Optional[str] = None  # Encriptado pelo OAuth callback
    company_id: Optional[str] = "default"  # FK: empresa a que esta config pertence

    @field_validator("company_id")
    @classmethod
    def validate_company_id(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                return "default"
        return v or "default"


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
    company_id: Optional[str] = "default"  # FK: empresa desta config
    available_companies: Optional[List[str]] = None  # Lista de company_ids com config


class EmailConfigTestResult(BaseModel):
    """Resultado do teste de ligação."""
    success: bool
    imap_connected: bool = False
    smtp_connected: bool = False
    gmail_api_connected: bool = False  # True se testou via Gmail API
    auth_method: str = "imap_smtp"  # "imap_smtp" | "google_oauth"
    error: Optional[str] = None


class UserEmailConfigDoc(BaseModel):
    """Documento da coleção user_email_configs (canónico).

    Representa uma config de email pessoal de um utilizador para
    uma empresa específica. A unicidade é (user_id, company_id).
    """
    id: str
    user_id: str                          # FK → db.users.id
    company_id: str                       # FK → db.company_email_configs.company_name
    email_address: str = ""
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465
    encrypted_password: str = ""
    google_refresh_token: Optional[str] = None
    google_access_token: Optional[str] = None
    google_email: Optional[str] = None
    auth_method: str = "none"             # "none" | "imap_smtp" | "google_oauth"
    oauth_connected_at: Optional[str] = None
    is_configured: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
