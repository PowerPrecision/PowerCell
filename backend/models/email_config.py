"""
====================================================================
MODELO: EmailConfig — Configuração de Email por Utilizador e Empresa
====================================================================

Suporta dois modos de autenticação:
1. Clássico: IMAP/SMTP com password (qualquer provedor)
2. Google OAuth 2.0: via Gmail API (refresh_token encriptado)

MULTI-EMPRESA + MULTI-CONTA (Pacote DN.4):
  O campo company_id associa a configuração a uma empresa (UCR).
  Um utilizador pode ter VÁRIAS configs por empresa (IMAP/SMTP ou OAuth).
  A unicidade é (user_id, company_id, email_address).
  `is_primary` marca a conta por omissão do perfil.

COLEÇÃO MONGODB: user_email_configs
INDEX: { user_id: 1, company_id: 1, email_address: 1 } (unique composto)

BACKWARD COMPATIBILITY:
  A conta primária também é guardada embebida no user.email_config (nested dict)
  sob a chave "company:<company_id>". A coleção user_email_configs é a fonte canónica.


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
    A unicidade é (user_id, company_id, email_address) — várias contas por perfil.
    """
    email_address: str
    password: Optional[str] = None  # Recebe em plain-text, será encriptada no endpoint
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465
    google_refresh_token: Optional[str] = None  # Encriptado pelo OAuth callback
    company_id: Optional[str] = "default"  # FK: empresa a que esta config pertence
    label: Optional[str] = None  # Nome amigável (ex: "Gmail pessoal")
    is_primary: Optional[bool] = None
    account_id: Optional[str] = None  # ID existente para actualizar uma conta

    @field_validator("company_id")
    @classmethod
    def validate_company_id(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                return "default"
        return v or "default"


class EmailAccountSummary(BaseModel):
    """Conta de email do perfil (sem secrets) — Pacote DN.4."""
    id: str
    company_id: Optional[str] = "default"
    email_address: Optional[str] = None
    label: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    is_configured: bool = False
    is_primary: bool = False
    has_password: bool = False
    has_google_oauth: bool = False
    auth_method: str = "none"
    google_email: Optional[str] = None
    oauth_connected_at: Optional[str] = None


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
    id: Optional[str] = None
    is_primary: bool = True
    label: Optional[str] = None
    accounts: Optional[List[EmailAccountSummary]] = None


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
    uma empresa. A unicidade é (user_id, company_id, email_address).
    Várias contas por perfil; `is_primary` indica a conta por omissão.
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
    is_primary: bool = False
    label: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
