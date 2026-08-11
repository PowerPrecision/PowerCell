"""Shared helpers and models for system diagnostics.

Extraído de `routes/diagnostics.py`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


def datetime_to_str(value: Any) -> Optional[str]:
    """Converte datetime ou qualquer valor para string ISO segura."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class ServiceStatus(BaseModel):
    """Estado de um serviço."""
    name: str
    configured: bool
    status: str  # "ok", "warning", "error", "not_configured"
    message: str
    last_activity: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    config_fields: Optional[List[str]] = None  # Campos que faltam configurar


class SystemDiagnostics(BaseModel):
    """Diagnóstico completo do sistema."""
    timestamp: str
    services: Dict[str, ServiceStatus]
    recent_errors: List[Dict[str, Any]]
    summary: Dict[str, int]


class TTLMigrationResult(BaseModel):
    """Resultado da migração TTL."""
    collection: str
    total_documents: int
    migrated: int
    already_migrated: int
    errors: int
    details: List[str]


class TTLMigrationResponse(BaseModel):
    """Resposta completa da migração TTL."""
    timestamp: str
    results: List[TTLMigrationResult]
    total_migrated: int
    message: str
