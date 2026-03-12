"""
====================================================================
MODELOS DE TAREFAS - CREDITOIMO
====================================================================
Modelos Pydantic para o sistema de tarefas.
====================================================================
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TaskCreate(BaseModel):
    """Criar nova tarefa."""
    title: str
    description: Optional[str] = None
    assigned_to: List[str]  # Lista de user_ids
    process_id: Optional[str] = None  # Se associada a um processo
    due_date: Optional[str] = None  # Data de vencimento (opcional) - formato ISO


class TaskUpdate(BaseModel):
    """Atualizar tarefa."""
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[List[str]] = None
    completed: Optional[bool] = None
    due_date: Optional[str] = None  # Data de vencimento (opcional)


class TaskResponse(BaseModel):
    """Resposta de tarefa."""
    id: str
    title: str
    description: Optional[str] = None
    assigned_to: List[str]  # Lista de user_ids
    assigned_to_names: Optional[List[str]] = None  # Nomes dos utilizadores
    process_id: Optional[str] = None
    process_name: Optional[str] = None  # Nome do cliente/processo
    created_by: str
    created_by_name: Optional[str] = None
    completed: bool = False
    completed_at: Optional[str] = None
    completed_by: Optional[str] = None
    due_date: Optional[str] = None  # Data de vencimento (opcional)
    is_overdue: Optional[bool] = None  # Se está atrasada
    days_until_due: Optional[int] = None  # Dias até vencer (negativo se atrasada)
    created_at: str
    updated_at: Optional[str] = None
