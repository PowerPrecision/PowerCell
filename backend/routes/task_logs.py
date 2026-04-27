"""
====================================================================
ROTAS DE TAREFAS ASSÍNCRONAS - TASKLOG
====================================================================
Endpoints para o Motor de Tarefas Assíncronas:
- GET /api/task-logs/active - Lista tarefas ativas do utilizador
- POST /api/task-logs/:id/acknowledge - Confirma visualização de tarefa concluída
- DELETE /api/task-logs/:id/cancel - Cancela tarefa pendente
- GET /api/task-logs - Lista todas as tarefas do utilizador

NOTE: Prefix changed from /tasks to /task-logs to avoid route
collision with routes/tasks.py which also uses prefix="/tasks".
====================================================================
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from models.task_log import TaskStatus, TaskType, TaskLogResponse, TaskLogListResponse
from services.auth import get_current_user
from services.task_log_service import task_log_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/task-logs", tags=["Async Tasks"])


# ====================================================================
# CONSTANTES PARA RESPOSTAS HTTP
# ====================================================================
HTTP_403_RESPONSE = {"description": "Forbidden - Acesso não autorizado"}
HTTP_404_RESPONSE = {"description": "Not Found - Tarefa não encontrada"}


# ====================================================================
# GET /API/TASK-LOGS/ACTIVE - TAREFAS ATIVAS
# ====================================================================
@router.get("/active", response_model=TaskLogListResponse)
async def get_active_tasks(
    user: dict = Depends(get_current_user)
):
    """
    Retorna todas as tarefas ativas do utilizador.
    
    Inclui:
    - Tarefas pendentes (status: pending)
    - Tarefas em processamento (status: processing)
    - Tarefas concluídas recentemente não confirmadas
    
    Este endpoint deve ser chamado pelo polling do frontend
    a cada 5 segundos para atualizar o estado das tarefas.
    """
    user_id = user.get("id")
    
    tasks = await task_log_service.get_active_tasks(user_id)
    
    # Contar por status
    active_count = sum(
        1 for t in tasks 
        if t.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]
    )
    completed_unacknowledged = sum(
        1 for t in tasks 
        if t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] and not t.acknowledged_at
    )
    
    return TaskLogListResponse(
        tasks=tasks,
        total=len(tasks),
        active_count=active_count,
        completed_unacknowledged=completed_unacknowledged
    )


# ====================================================================
# GET /API/TASK-LOGS/:TASK_ID - DETALHES DA TAREFA
# ====================================================================
@router.get("/{task_id}", response_model=TaskLogResponse)
async def get_task_details(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Retorna os detalhes de uma tarefa específica.
    """
    task = await task_log_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    # Verificar se pertence ao utilizador
    if task.user_id != user.get("id") and user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")
    
    return task


# ====================================================================
# POST /API/TASK-LOGS/:TASK_ID/ACKNOWLEDGE - CONFIRMAR VISUALIZAÇÃO
# ====================================================================
@router.post("/{task_id}/acknowledge")
async def acknowledge_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Marca uma tarefa como visualizada/confirmada pelo utilizador.
    
    Isto remove a tarefa da lista de "ativas" no frontend,
    sinalizando que o utilizador já viu o resultado.
    
    Retorna 200 se confirmada com sucesso.
    """
    task = await task_log_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    if task.user_id != user.get("id"):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")
    
    success = await task_log_service.acknowledge_task(task_id, user.get("id"))
    
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Não foi possível confirmar a tarefa"
        )
    
    return {
        "success": True,
        "message": "Tarefa confirmada",
        "task_id": task_id
    }


# ====================================================================
# DELETE /API/TASK-LOGS/:TASK_ID/CANCEL - CANCELAR TAREFA
# ====================================================================
@router.delete("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Cancela uma tarefa pendente.
    
    Só é possível cancelar tarefas em status 'pending'.
    Tarefas em processamento ou concluídas não podem ser canceladas.
    """
    task = await task_log_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    if task.user_id != user.get("id") and user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")
    
    if task.status != TaskStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível cancelar uma tarefa em status '{task.status.value}'"
        )
    
    success = await task_log_service.cancel_task(task_id, user.get("id"))
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar a tarefa"
        )
    
    return {
        "success": True,
        "message": "Tarefa cancelada",
        "task_id": task_id
    }


# ====================================================================
# GET /API/TASK-LOGS - LISTAR TAREFAS DO UTILIZADOR
# ====================================================================
@router.get("", response_model=TaskLogListResponse)
async def list_user_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filtrar por status"),
    task_type: Optional[TaskType] = Query(None, description="Filtrar por tipo"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user: dict = Depends(get_current_user)
):
    """
    Lista todas as tarefas do utilizador com filtros opcionais.
    
    Args:
        status: Filtrar por status (pending, processing, completed, failed, cancelled)
        task_type: Filtrar por tipo (PDF_GEN, AI_ANALYSIS, etc.)
        limit: Número máximo de resultados (default: 50)
        skip: Número de resultados a saltar (para paginação)
    """
    user_id = user.get("id")
    
    tasks, total = await task_log_service.get_user_tasks(
        user_id,
        status=status,
        task_type=task_type,
        limit=limit,
        skip=skip
    )
    
    active_count = sum(
        1 for t in tasks 
        if t.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]
    )
    completed_unacknowledged = sum(
        1 for t in tasks 
        if t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] and not t.acknowledged_at
    )
    
    return TaskLogListResponse(
        tasks=tasks,
        total=total,
        active_count=active_count,
        completed_unacknowledged=completed_unacknowledged
    )


# ====================================================================
# DELETE /API/TASK-LOGS/:TASK_ID - ELIMINAR TAREFA
# ====================================================================
@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Elimina uma tarefa do histórico.
    
    Só é possível eliminar tarefas concluídas, falhadas ou canceladas.
    Tarefas pendentes ou em processamento devem ser canceladas primeiro.
    """
    task = await task_log_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    if task.user_id != user.get("id") and user.get("role") not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a esta tarefa")
    
    if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
        raise HTTPException(
            status_code=400,
            detail="Não é possível eliminar uma tarefa em execução. Cancele primeiro."
        )
    
    result = await db.task_logs.delete_one(
        {"$or": [{"task_id": task_id}, {"id": task_id}]}
    )
    
    if result.deleted_count > 0:
        return {
            "success": True,
            "message": "Tarefa eliminada",
            "task_id": task_id
        }
    
    raise HTTPException(
        status_code=500,
        detail="Erro ao eliminar tarefa"
    )
