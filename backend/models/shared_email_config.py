"""
====================================================================
MODELO - CONFIGURAÇÃO DE EMAIL PARTILHADO POR ROLE
====================================================================
Modelos Pydantic para gerir configurações de email partilhadas
por departamento/role (ex: 'indexacao', 'suporte').

ARMAZENAMENTO:
- Coleção MongoDB: `shared_role_email_configs`
- O `google_refresh_token` é encriptado com Fernet via encryption_service
  antes de ser guardado na base de dados.

FLUXO DE CONFIGURAÇÃO:
1. Admin clica "Autenticar com o Google" no painel de administração
2. Frontend chama GET /api/admin/shared-email/google/login?role=indexacao
3. Admin autoriza na página da Google
4. Callback guarda o refresh_token encriptado neste modelo

ISOLAMENTO:
- Cada role tem a sua própria configuração de email
- O worker de sync utiliza esta config para descarregar emails da
  caixa partilhada do departamento via Gmail API
====================================================================
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SharedEmailAuthMethod(str, Enum):
    """Método de autenticação do email partilhado."""
    NONE = "none"
    GOOGLE_OAUTH = "google_oauth"
    IMAP_SMTP = "imap_smtp"


class SharedEmailConfigCreate(BaseModel):
    """Payload para criar/atualizar config de email partilhado (Admin).

    O google_refresh_token é preenchido automaticamente pelo fluxo OAuth.
    Não deve ser enviado manualmente pelo frontend.
    """
    role: str = Field(..., description="Role do departamento (ex: indexacao)")
    email_address: str = Field("", description="Endereço de email da caixa partilhada")
    display_name: str = Field("", description="Nome visível no painel (ex: 'Email de Indexação')")
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465
    encrypted_password: str = Field("", description="Password IMAP (encriptada)")


class SharedEmailConfigResponse(BaseModel):
    """Resposta GET — nunca inclui tokens ou passwords reais."""
    role: str
    email_address: Optional[str] = None
    display_name: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    is_configured: bool = False
    auth_method: str = SharedEmailAuthMethod.NONE.value
    has_google_oauth: bool = False
    google_email: Optional[str] = None
    has_imap_password: bool = False
    oauth_connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    total_emails_synced: int = 0
    updated_at: Optional[str] = None


class SharedEmailConfigListResponse(BaseModel):
    """Lista de todas as configs de email partilhado."""
    configs: List[SharedEmailConfigResponse]
    total: int


class SharedEmailOAuthLoginResponse(BaseModel):
    """Resposta do endpoint de login OAuth."""
    authorization_url: str
    state: str
    redirect_uri: str
    role: str
