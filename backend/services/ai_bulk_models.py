"""Pydantic models for AI bulk import routes.

Extraído de `routes/ai_bulk.py`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SingleAnalysisResult(BaseModel):
    """Resultado da análise de um único documento pela IA.

    Usado como response model do endpoint /analyze-single. Contém
    informação sobre o sucesso da análise, campos extraídos, e
    potenciais conflitos com dados existentes do cliente.

    Attributes:
        success: Se a análise foi concluída com sucesso.
        client_name: Nome do cliente identificado (ou "N/A").
        filename: Nome do ficheiro analisado.
        document_type: Tipo de documento identificado pela IA.
        fields_extracted: Lista de nomes dos campos extraídos.
        updated: Se os dados do processo foram atualizados.
        error: Mensagem de erro (se houver).
        conflicts: Detalhes de conflitos com dados existentes.
    """
    success: bool
    client_name: str
    filename: str
    document_type: str = ""
    fields_extracted: List[str] = []
    updated: bool = False
    error: Optional[str] = None
    conflicts: Optional[Dict[str, Any]] = None


class ImportSessionRequest(BaseModel):
    """Request para iniciar uma sessão de importação de documentos.

    Attributes:
        total_files: Número total de ficheiros a processar.
        folder_name: Nome da pasta no S3 (opcional).
        client_id: ID do cliente associado (opcional).
    """
    total_files: int
    folder_name: Optional[str] = None
    client_id: Optional[str] = None


class ImportSessionResponse(BaseModel):
    """Response da criação de uma sessão de importação.

    Attributes:
        session_id: Identificador único da sessão.
        message: Mensagem de confirmação.
    """
    session_id: str
    message: str


class UpdateSessionRequest(BaseModel):
    """Request para atualizar o progresso de uma sessão de importação.

    Enviado pelo frontend periodicamente para reportar progresso.

    Attributes:
        processed: Número de ficheiros já processados.
        errors: Número de ficheiros com erro.
        error_message: Mensagem de erro do último ficheiro falhado.
        current_step: Descrição da etapa actual (mostrado no centro de operações).
    """
    processed: Optional[int] = None
    errors: Optional[int] = None
    error_message: Optional[str] = None
    current_step: Optional[str] = None


class AggregatedSessionRequest(BaseModel):
    """Request para iniciar sessão de importação agregada."""
    total_files: int
    client_id: Optional[str] = None
    client_name: Optional[str] = None


class AggregatedSessionResponse(BaseModel):
    """Response da sessão de importação agregada."""
    session_id: str
    message: str
    aggregation_mode: bool = True


class AggregatedFileResult(BaseModel):
    """Resultado do processamento de um ficheiro na sessão agregada."""
    success: bool
    client_name: str
    filename: str
    document_type: str = ""
    fields_extracted: List[str] = []
    aggregated: bool = True
    error: Optional[str] = None


class AggregatedFinishResponse(BaseModel):
    """Response da finalização da sessão agregada."""
    success: bool
    message: str
    clients_updated: int
    total_documents: int
    errors: int
    summary: Dict[str, Any] = {}


class ProgressUpdateRequest(BaseModel):
    """Request para actualizar progresso de um job."""
    processed: Optional[int] = None
    errors: Optional[int] = None
    message: Optional[str] = None

