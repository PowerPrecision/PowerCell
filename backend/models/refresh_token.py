"""
====================================================================
MODELO DE REFRESH TOKENS - AUTENTICAÇÃO SEGURA
====================================================================
Sistema de refresh tokens com rotação segura para sessões longas.
Access tokens têm duração curta (15 min), refresh tokens 7 dias.
====================================================================
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RefreshToken(BaseModel):
    """Modelo de refresh token armazenado na BD."""
    id: str  # ID único do token
    user_id: str  # ID do utilizador
    token_hash: str  # Hash do token (não guardamos o token em claro)
    device_info: Optional[str] = None  # User-Agent ou identificador do dispositivo
    ip_address: Optional[str] = None  # IP de criação
    created_at: str  # Data de criação (ISO format)
    expires_at: str  # Data de expiração (ISO format)
    revoked: bool = False  # Se foi revogado
    revoked_at: Optional[str] = None  # Quando foi revogado
    replaced_by: Optional[str] = None  # ID do token que substituiu este


class RefreshTokenCreate(BaseModel):
    """Request para criar novo refresh token."""
    user_id: str
    device_info: Optional[str] = None
    ip_address: Optional[str] = None


class RefreshTokenResponse(BaseModel):
    """Response com tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Segundos até expiração do access token


class RefreshRequest(BaseModel):
    """Request para renovar tokens."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Request para fazer logout (revogar refresh token)."""
    refresh_token: Optional[str] = None  # Se não fornecido, revoga todos os tokens do utilizador
