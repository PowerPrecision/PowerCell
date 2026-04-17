"""
====================================================================
MODELO: CompanyEmailConfig
====================================================================
Configuração padrão de IMAP/SMTP por empresa.

Quando um utilizador não tem config individual, o sistema herda os
servidores (IMAP/SMTP) da empresa a que pertence. A password e o
email_address continuam a ser individuais — apenas os *servidores*
são partilhados.

COLEÇÃO MONGODB: company_email_configs
INDEX: { company_name: 1 } (unique)

CAMINHO DA HERANÇA:
  1. User Config (email_config embedded no documento do user)
  2. Company Config (este modelo — servidores padrão da empresa)
  3. System Config (system_config.email — globals)
====================================================================
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CompanyEmailConfigCreate(BaseModel):
    """Payload para criar/atualizar config de email por empresa."""
    company_name: str
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465


class CompanyEmailConfigResponse(BaseModel):
    """Resposta GET — campos visíveis no frontend."""
    id: str
    company_name: str
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    has_encrypted_password: bool = False
    total_users: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CompanyEmailConfigListResponse(BaseModel):
    """Lista de configs com total."""
    configs: List[CompanyEmailConfigResponse]
    total: int
