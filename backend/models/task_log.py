"""
====================================================================
MODELO DE TAREFAS ASSÍNCRONAS - TASKLOG
====================================================================
Sistema de tarefas assíncronas para operações pesadas.
Permite que o utilizador continue a usar o CRM enquanto a tarefa
corre em background, recebendo notificação quando terminar.
====================================================================
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    """Estados possíveis de uma tarefa assíncrona."""
    PENDING = "pending"        # Aguardando execução
    PROCESSING = "processing"  # Em execução
    COMPLETED = "completed"    # Concluída com sucesso
    FAILED = "failed"          # Falhou
    CANCELLED = "cancelled"    # Cancelada pelo utilizador


class TaskType(str, Enum):
    """Tipos de tarefas assíncronas disponíveis."""
    PDF_GEN = "PDF_GEN"                    # Geração de PDF
    AI_ANALYSIS = "AI_ANALYSIS"            # Análise de IA
    EMAIL_SEND = "EMAIL_SEND"              # Envio de emails
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"    # Upload de documentos
    BULK_IMPORT = "BULK_IMPORT"            # Importação em massa
    REPORT_GEN = "REPORT_GEN"              # Geração de relatórios
    DATA_EXPORT = "DATA_EXPORT"            # Exportação de dados
    DOCUMENT_CATEGORIZE = "DOC_CATEGORIZE" # Categorização automática
    TEMPLATE_FILL = "TEMPLATE_FILL"        # Preenchimento de templates
    S3_UPLOAD = "S3_UPLOAD"                # Upload para S3
    CUSTOM = "CUSTOM"                      # Tarefa customizada


class TaskLogCreate(BaseModel):
    """Dados para criar uma nova tarefa assíncrona."""
    task_type: TaskType
    user_id: str
    process_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskLogUpdate(BaseModel):
    """Dados para actualizar uma tarefa."""
    status: Optional[TaskStatus] = None
    progress: Optional[int] = None
    progress_message: Optional[str] = None
    result_url: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskLogResponse(BaseModel):
    """Resposta de uma tarefa assíncrona."""
    id: str = Field(..., description="ID único da tarefa (UUID)")
    task_id: str = Field(..., description="ID da tarefa para tracking")
    user_id: str = Field(..., description="ID do utilizador que criou a tarefa")
    task_type: TaskType = Field(..., description="Tipo de tarefa")
    status: TaskStatus = Field(..., description="Estado atual da tarefa")
    title: str = Field(..., description="Título descritivo da tarefa")
    description: Optional[str] = Field(None, description="Descrição detalhada")
    
    # Progresso
    progress: int = Field(0, ge=0, le=100, description="Progresso (0-100)")
    progress_message: Optional[str] = Field(None, description="Mensagem de progresso atual")
    
    # Referências
    process_id: Optional[str] = Field(None, description="ID do processo associado")
    process_name: Optional[str] = Field(None, description="Nome do cliente/processo")
    
    # Resultados
    result_url: Optional[str] = Field(None, description="URL do resultado (ex: PDF gerado)")
    result_data: Optional[Dict[str, Any]] = Field(None, description="Dados adicionais do resultado")
    error_message: Optional[str] = Field(None, description="Mensagem de erro se falhou")
    
    # Metadados
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadados adicionais")
    
    # Timestamps
    created_at: str = Field(..., description="Data de criação")
    started_at: Optional[str] = Field(None, description="Data de início da execução")
    completed_at: Optional[str] = Field(None, description="Data de conclusão")
    
    # Configuração
    acknowledge_required: bool = Field(
        True, 
        description="Se requer confirmação do utilizador antes de ser removida da lista"
    )
    acknowledged_at: Optional[str] = Field(None, description="Data de confirmação pelo utilizador")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "task_id": "task_abc123",
                "user_id": "user_123",
                "task_type": "PDF_GEN",
                "status": "processing",
                "title": "Gerando contrato CPCV",
                "description": "A gerar PDF do contrato promessa compra e venda",
                "progress": 45,
                "progress_message": "A processar template...",
                "process_id": "proc_123",
                "process_name": "João Silva",
                "result_url": None,
                "created_at": "2024-01-15T10:30:00Z",
                "acknowledge_required": True
            }
        }


class TaskLogListResponse(BaseModel):
    """Lista de tarefas assíncronas."""
    tasks: list[TaskLogResponse]
    total: int
    active_count: int = Field(..., description="Tarefas pendentes ou em processamento")
    completed_unacknowledged: int = Field(..., description="Tarefas concluídas não confirmadas")
