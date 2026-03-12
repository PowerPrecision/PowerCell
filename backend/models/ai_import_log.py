"""
====================================================================
AI Import Logs Model - PowerCell
====================================================================
Modelo para logs de importações IA com detalhes de processamento.
====================================================================
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ImportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    PENDING = "pending"


class DocumentImportResult(BaseModel):
    """Resultado da importação de um documento individual."""
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    status: ImportStatus = ImportStatus.PENDING
    document_type: Optional[str] = None
    confidence: Optional[float] = None
    destination_folder: Optional[str] = None
    extracted_fields: Optional[Dict[str, Any]] = None
    applied_fields: Optional[List[str]] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None


class AIImportLog(BaseModel):
    """Log completo de uma importação IA."""
    id: str = Field(..., description="ID único do log")
    process_id: str = Field(..., description="ID do processo/cliente")
    client_name: str = Field(..., description="Nome do cliente")
    
    # Metadados da importação
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    
    # Estatísticas gerais
    total_documents: int = 0
    success_count: int = 0
    error_count: int = 0
    partial_count: int = 0
    
    # Status geral
    status: ImportStatus = ImportStatus.PENDING
    
    # Duração total
    duration_ms: Optional[int] = None
    
    # Resultados por documento
    documents: List[DocumentImportResult] = []
    
    # Campos preenchidos automaticamente
    auto_filled_fields: Optional[Dict[str, Any]] = None
    
    # Campos com conflitos (escolhas do utilizador)
    conflict_resolutions: Optional[List[Dict[str, Any]]] = None
    
    # Observações gerais
    notes: Optional[str] = None


class AIImportLogCreate(BaseModel):
    """Dados para criar um novo log."""
    process_id: str
    client_name: str
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None


class AIImportLogSummary(BaseModel):
    """Resumo de um log para listagem."""
    id: str
    process_id: str
    client_name: str
    created_at: datetime
    created_by_name: Optional[str] = None
    status: ImportStatus
    total_documents: int
    success_count: int
    error_count: int
    duration_ms: Optional[int] = None
