"""
====================================================================
MODELO: UserCompanyRole — Associação Muitos-para-Muitos
====================================================================
Tabela intermédia que liga Utilizadores a Empresas com um Role específico.

Um utilizador pode pertencer a várias empresas e ter vários cargos na
mesma empresa (Pacote EA):
  - Ex: Consultor na "Power Real Estate", Intermediário na "Precision Crédito"
  - Ex: Diretor E Consultor na mesma "Empresa A"

COLEÇÃO MONGODB: user_company_roles
INDEX: { user_id: 1, company_id: 1, role: 1 } (unique composto)
INDEX: { company_id: 1 }
INDEX: { user_id: 1, is_default: 1 } (sparse, para lookup rápido da empresa padrão)

CAMPOS:
  - user_id: FK para db.users.id
  - company_id: FK para db.company_email_configs.id (ou company_name string)
  - company_name: Nome da empresa (denormalizado para queries rápidas)
  - role: Papel do utilizador nesta empresa (enum de UserRoleEnum)
  - is_default: Se True, é a empresa que carrega no login
  - created_at / updated_at: timestamps

BACKWARD COMPATIBILITY:
  - O campo `company` no user document continua a existir como fallback.
  - Se user_company_roles estiver vazio, o sistema usa `user.company`.
  - A migração deve popular user_company_roles a partir do campo `company` existente.
====================================================================
"""

from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict
from datetime import datetime, timezone
from enum import Enum


class CompanyRoleEnum(str, Enum):
    """Roles que um utilizador pode ter numa empresa específica.

    Alinhado com UserRoleEnum (exceto o pseudo-role `cliente`).
    `admin` é o cargo canónico de administrador; `administrativo` é
    Apoio Administrativo — cargos distintos, não aliases.
    """
    CONSULTOR = "consultor"
    INTERMEDIARIO = "intermediario"
    ADMINISTRATIVO = "administrativo"
    INDEXACAO = "indexacao"
    DIRETOR = "diretor"
    CEO = "ceo"
    ADMIN = "admin"
    PARCEIRO = "parceiro"


class UserRoleAssignBody(BaseModel):
    """Payload compacto para POST /admin/users/{user_id}/roles."""
    company_id: str
    company_name: Optional[str] = None
    role: str
    is_default: bool = False

    @field_validator("role")
    @classmethod
    def validate_assign_role(cls, v):
        valid_roles = [e.value for e in CompanyRoleEnum]
        if v not in valid_roles:
            raise ValueError(f"Role inválido: {v}. Válidos: {valid_roles}")
        return v


class UserCompanyRoleCreate(BaseModel):
    """Payload para associar um utilizador a uma empresa com um role."""
    user_id: str
    company_id: str  # ID ou nome da empresa
    company_name: str  # Nome da empresa (denormalizado)
    role: str  # Role nesta empresa
    is_default: bool = False
    # ── Campos específicos por empresa (multi-tenant) ──
    signature: Optional[str] = None  # Assinatura de email HTML/Texto para esta empresa
    professional_phone: Optional[str] = None  # Telefone profissional específico desta empresa
    job_title: Optional[str] = None  # Cargo específico nesta empresa
    display_name: Optional[str] = None  # PACOTE DF — Nome de exibição específico desta empresa
    # PACOTE DF — Preferências de notificação (14 booleans) por-UCR.
    # Quando None, o consumidor cai para o store global (db.notification_preferences).
    notification_preferences: Optional[Dict[str, bool]] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        valid_roles = [e.value for e in CompanyRoleEnum]
        if v not in valid_roles:
            raise ValueError(f"Role inválido: {v}. Válidos: {valid_roles}")
        return v

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Nome da empresa é obrigatório")
        return v.strip()


class UserCompanyRoleUpdate(BaseModel):
    """Payload para atualizar uma associação existente."""
    role: Optional[str] = None
    is_default: Optional[bool] = None
    # ── Campos específicos por empresa (multi-tenant) ──
    signature: Optional[str] = None  # Assinatura de email HTML/Texto para esta empresa
    professional_phone: Optional[str] = None  # Telefone profissional específico desta empresa
    job_title: Optional[str] = None  # Cargo específico nesta empresa
    display_name: Optional[str] = None  # PACOTE DF — Nome de exibição específico desta empresa
    # PACOTE DF — Preferências de notificação por-UCR (fallback ao store global se None).
    notification_preferences: Optional[Dict[str, bool]] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v is not None:
            valid_roles = [e.value for e in CompanyRoleEnum]
            if v not in valid_roles:
                raise ValueError(f"Role inválido: {v}. Válidos: {valid_roles}")
        return v


class UserCompanyRoleResponse(BaseModel):
    """Resposta GET — associação visível no frontend."""
    id: str
    user_id: str
    company_id: str
    company_name: str
    role: str
    is_default: bool = False
    # ── Campos específicos por empresa (multi-tenant) ──
    signature: Optional[str] = None  # Assinatura de email HTML/Texto para esta empresa
    professional_phone: Optional[str] = None  # Telefone profissional específico desta empresa
    job_title: Optional[str] = None  # Cargo específico nesta empresa
    display_name: Optional[str] = None  # PACOTE DF — Nome de exibição específico desta empresa
    # PACOTE DF — Preferências de notificação por-UCR (14 booleans) ou None (fallback global).
    notification_preferences: Optional[Dict[str, bool]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserCompaniesResponse(BaseModel):
    """Lista de empresas com roles para um utilizador (para o ContextSwitcher)."""
    companies: List[dict]  # [{ company_id, company_name, role, is_default }]
    active_company_id: Optional[str] = None  # Empresa ativa no contexto
