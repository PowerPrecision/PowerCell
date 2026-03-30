from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum


class UserRoleEnum(str, Enum):
    """
    Enum para roles de utilizador - garante type-safety e evita magic strings.
    Herda de str para ser serializável em JSON automaticamente.
    """
    CLIENTE = "cliente"
    CONSULTOR = "consultor"
    INTERMEDIARIO = "intermediario"  # Intermediário de Crédito (antes: mediador)
    MEDIADOR = "mediador"  # Legacy alias
    ADMINISTRATIVO = "administrativo"  # Administrativo(a) - gestão administrativa
    INDEXACAO = "indexacao"  # Indexação - só visualiza dados e gere documentos (upload/delete)
    DIRETOR = "diretor"  # Diretor(a) - gestão de direção
    CEO = "ceo"  # Between admin and staff - can manage basic things + consultor/intermediário tasks
    ADMIN = "admin"
    
    @classmethod
    def from_string(cls, role: str) -> "UserRoleEnum":
        """Converte string para enum, com fallback para CLIENTE."""
        try:
            return cls(role.lower()) if role else cls.CLIENTE
        except ValueError:
            return cls.CLIENTE


class UserRole:
    """
    Classe helper para verificações de permissões.
    Mantida para compatibilidade com código existente.
    Usa UserRoleEnum internamente para type-safety.
    """
    # Constantes de role (strings) - para compatibilidade
    CLIENTE = UserRoleEnum.CLIENTE.value
    CONSULTOR = UserRoleEnum.CONSULTOR.value
    INTERMEDIARIO = UserRoleEnum.INTERMEDIARIO.value
    MEDIADOR = UserRoleEnum.MEDIADOR.value
    ADMINISTRATIVO = UserRoleEnum.ADMINISTRATIVO.value
    INDEXACAO = UserRoleEnum.INDEXACAO.value
    DIRETOR = UserRoleEnum.DIRETOR.value
    CEO = UserRoleEnum.CEO.value
    ADMIN = UserRoleEnum.ADMIN.value
    
    # Lista de todos os roles válidos
    ALL_ROLES = [e.value for e in UserRoleEnum]
    
    # Grupos de roles para permissões
    STAFF_ROLES = [
        UserRoleEnum.CONSULTOR.value,
        UserRoleEnum.INTERMEDIARIO.value,
        UserRoleEnum.MEDIADOR.value,
        UserRoleEnum.ADMINISTRATIVO.value,
        UserRoleEnum.INDEXACAO.value,
        UserRoleEnum.DIRETOR.value,
        UserRoleEnum.CEO.value,
        UserRoleEnum.ADMIN.value,
    ]
    
    # Roles que podem gerir documentos (upload/delete)
    DOCUMENT_ROLES = [
        UserRoleEnum.INDEXACAO.value,
        UserRoleEnum.ADMINISTRATIVO.value,
        UserRoleEnum.CONSULTOR.value,
        UserRoleEnum.INTERMEDIARIO.value,
        UserRoleEnum.MEDIADOR.value,
        UserRoleEnum.DIRETOR.value,
        UserRoleEnum.CEO.value,
        UserRoleEnum.ADMIN.value,
    ]
    
    MANAGEMENT_ROLES = [
        UserRoleEnum.DIRETOR.value,
        UserRoleEnum.CEO.value,
        UserRoleEnum.ADMIN.value,
    ]
    
    @classmethod
    def is_valid_role(cls, role: str) -> bool:
        """Verifica se o role é válido."""
        return role in cls.ALL_ROLES
    
    @classmethod
    def can_act_as_consultor(cls, role: str) -> bool:
        """Check if role can perform consultor tasks"""
        return role in [cls.CONSULTOR, cls.DIRETOR, cls.CEO, cls.ADMIN, cls.ADMINISTRATIVO]
    
    @classmethod
    def can_act_as_intermediario(cls, role: str) -> bool:
        """Check if role can perform intermediário de crédito tasks"""
        return role in [cls.INTERMEDIARIO, cls.MEDIADOR, cls.DIRETOR, cls.CEO, cls.ADMIN, cls.ADMINISTRATIVO]
    
    @classmethod
    def can_act_as_mediador(cls, role: str) -> bool:
        """Legacy alias for can_act_as_intermediario"""
        return cls.can_act_as_intermediario(role)
    
    @classmethod
    def is_staff(cls, role: str) -> bool:
        """Check if role is staff (not cliente)"""
        return role != cls.CLIENTE
    
    @classmethod
    def can_view_all_notifications(cls, role: str) -> bool:
        """Check if role can view all notifications (admin, CEO, diretor)"""
        return role in cls.MANAGEMENT_ROLES
    
    @classmethod
    def can_manage_users(cls, role: str) -> bool:
        """Check if role can manage other users"""
        return role in [cls.ADMIN, cls.CEO]
    
    @classmethod
    def can_access_admin_panel(cls, role: str) -> bool:
        """Check if role can access admin panel"""
        return role in cls.MANAGEMENT_ROLES
    
    @classmethod
    def can_manage_documents(cls, role: str) -> bool:
        """Check if role can manage documents (upload, rename, delete)"""
        return role in cls.DOCUMENT_ROLES
    
    @classmethod
    def is_document_only(cls, role: str) -> bool:
        """Check if role is document-only (indexacao)"""
        return role == cls.INDEXACAO


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone: Optional[str] = None
    role: str
    company: Optional[str] = None  # Empresa do utilizador
    is_active: Optional[bool] = True
    created_at: Optional[str] = None
    onedrive_folder: Optional[str] = None
    permissions: Optional[dict] = None  # Permissões específicas do utilizador


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    role: str
    company: Optional[str] = None  # Empresa do utilizador
    onedrive_folder: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None  # Empresa do utilizador
    is_active: Optional[bool] = None
    onedrive_folder: Optional[str] = None
    password: Optional[str] = None  # Nova password (apenas admin pode alterar)
    permissions: Optional[dict] = None  # Permissões específicas do utilizador
