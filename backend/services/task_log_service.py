"""
====================================================================
SERVIÇO DE TAREFAS ASSÍNCRONAS - TASKLOG SERVICE
====================================================================
Gerencia o ciclo de vida das tarefas assíncronas:
- Criação de tarefas
- Atualização de progresso
- Marcação como concluída/falhada
- Listagem de tarefas ativas
====================================================================
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from database import db
from models.task_log import TaskStatus, TaskType, TaskLogCreate, TaskLogUpdate, TaskLogResponse

logger = logging.getLogger(__name__)

# Nome da coleção no MongoDB
TASK_LOG_COLLECTION = "task_logs"

# Tempo para manter tarefas concluídas na lista (para polling)
COMPLETED_TASK_TTL_HOURS = 24

# Tempo para manter tarefas concluídas não confirmadas
UNACKNOWLEDGED_TASK_TTL_HOURS = 72


class TaskLogService:
    """Serviço para gestão de tarefas assíncronas."""
    
    @staticmethod
    async def create_task(
        task_type: TaskType,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        process_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        acknowledge_required: bool = True
    ) -> TaskLogResponse:
        """
        Cria uma nova tarefa assíncrona.
        
        Args:
            task_type: Tipo de tarefa (PDF_GEN, AI_ANALYSIS, etc.)
            user_id: ID do utilizador que criou a tarefa
            title: Título descritivo da tarefa
            description: Descrição detalhada (opcional)
            process_id: ID do processo associado (opcional)
            metadata: Metadados adicionais (opcional)
            acknowledge_required: Se requer confirmação do utilizador
            
        Returns:
            TaskLogResponse com os dados da tarefa criada
        """
        now = datetime.now(timezone.utc).isoformat()
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        doc_id = str(uuid.uuid4())
        
        # Buscar nome do processo se disponível
        process_name = None
        if process_id:
            process = await db.processes.find_one({"id": process_id}, {"client_name": 1})
            if process:
                process_name = process.get("client_name")
        
        task_doc = {
            "id": doc_id,
            "task_id": task_id,
            "user_id": user_id,
            "task_type": task_type.value if isinstance(task_type, TaskType) else task_type,
            "status": TaskStatus.PENDING.value,
            "title": title,
            "description": description,
            "progress": 0,
            "progress_message": "Aguardando execução...",
            "process_id": process_id,
            "process_name": process_name,
            "result_url": None,
            "result_data": None,
            "error_message": None,
            "metadata": metadata or {},
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "acknowledge_required": acknowledge_required,
            "acknowledged_at": None
        }
        
        await db[TASK_LOG_COLLECTION].insert_one(task_doc)
        
        # Remover _id antes de retornar
        task_doc.pop("_id", None)
        
        logger.info(f"[TaskLog] Tarefa criada: {task_id} - {title} (user: {user_id})")
        
        return TaskLogResponse(**task_doc)
    
    @staticmethod
    async def update_task(
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        progress_message: Optional[str] = None,
        result_url: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[TaskLogResponse]:
        """
        Atualiza uma tarefa existente.
        
        Args:
            task_id: ID da tarefa (task_xxx) ou ID do documento
            status: Novo status (opcional)
            progress: Progresso 0-100 (opcional)
            progress_message: Mensagem de progresso (opcional)
            result_url: URL do resultado (opcional)
            result_data: Dados do resultado (opcional)
            error_message: Mensagem de erro (opcional)
            metadata: Metadados adicionais (opcional)
            
        Returns:
            TaskLogResponse atualizada ou None se não encontrada
        """
        now = datetime.now(timezone.utc).isoformat()
        
        updates = {}
        
        if status is not None:
            updates["status"] = status.value if isinstance(status, TaskStatus) else status
            
            # Actualizar timestamps baseado no status
            if status == TaskStatus.PROCESSING:
                updates["started_at"] = now
                if progress_message is None:
                    updates["progress_message"] = "Em processamento..."
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                updates["completed_at"] = now
        
        if progress is not None:
            updates["progress"] = max(0, min(100, progress))
        
        if progress_message is not None:
            updates["progress_message"] = progress_message
        
        if result_url is not None:
            updates["result_url"] = result_url
        
        if result_data is not None:
            updates["result_data"] = result_data
        
        if error_message is not None:
            updates["error_message"] = error_message
        
        if metadata is not None:
            updates["metadata"] = metadata
        
        if not updates:
            return None
        
        # Tentar encontrar por task_id ou id
        result = await db[TASK_LOG_COLLECTION].find_one_and_update(
            {"$or": [{"task_id": task_id}, {"id": task_id}]},
            {"$set": updates},
            return_document=True
        )
        
        if result:
            result.pop("_id", None)
            logger.info(f"[TaskLog] Tarefa atualizada: {task_id} - status: {updates.get('status', 'N/A')}")
            return TaskLogResponse(**result)
        
        logger.warning(f"[TaskLog] Tarefa não encontrada: {task_id}")
        return None
    
    @staticmethod
    async def get_task(task_id: str) -> Optional[TaskLogResponse]:
        """Obtém uma tarefa pelo ID."""
        result = await db[TASK_LOG_COLLECTION].find_one(
            {"$or": [{"task_id": task_id}, {"id": task_id}]},
            {"_id": 0}
        )
        
        if result:
            return TaskLogResponse(**result)
        return None
    
    @staticmethod
    async def get_active_tasks(user_id: str) -> List[TaskLogResponse]:
        """
        Obtém todas as tarefas ativas (pending, processing) e recentemente concluídas
        que ainda não foram confirmadas pelo utilizador.
        """
        now = datetime.now(timezone.utc)
        
        # Calcular cutoff para tarefas concluídas recentemente
        recent_cutoff = (now - timedelta(hours=1)).isoformat()
        
        query = {
            "user_id": user_id,
            "$or": [
                # Tarefas pendentes ou em processamento
                {"status": {"$in": [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]}},
                # Tarefas concluídas recentemente não confirmadas
                {
                    "status": {"$in": [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]},
                    "acknowledged_at": None,
                    "completed_at": {"$gte": recent_cutoff}
                }
            ]
        }
        
        cursor = db[TASK_LOG_COLLECTION].find(query, {"_id": 0}).sort("created_at", -1)
        tasks = await cursor.to_list(length=50)
        
        return [TaskLogResponse(**task) for task in tasks]
    
    @staticmethod
    async def get_user_tasks(
        user_id: str,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 50,
        skip: int = 0
    ) -> tuple[List[TaskLogResponse], int]:
        """
        Obtém tarefas do utilizador com filtros.
        
        Returns:
            Tuple de (lista de tarefas, total)
        """
        query = {"user_id": user_id}
        
        if status:
            query["status"] = status.value if isinstance(status, TaskStatus) else status
        
        if task_type:
            query["task_type"] = task_type.value if isinstance(task_type, TaskType) else task_type
        
        cursor = db[TASK_LOG_COLLECTION].find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        tasks = await cursor.to_list(length=limit)
        total = await db[TASK_LOG_COLLECTION].count_documents(query)
        
        return [TaskLogResponse(**task) for task in tasks], total
    
    @staticmethod
    async def acknowledge_task(task_id: str, user_id: str) -> bool:
        """
        Marca uma tarefa como confirmada pelo utilizador.
        Remove-a da lista de "ativas" no frontend.
        """
        now = datetime.now(timezone.utc).isoformat()
        
        result = await db[TASK_LOG_COLLECTION].update_one(
            {
                "$or": [{"task_id": task_id}, {"id": task_id}],
                "user_id": user_id
            },
            {"$set": {"acknowledged_at": now}}
        )
        
        if result.modified_count > 0:
            logger.info(f"[TaskLog] Tarefa confirmada: {task_id}")
            return True
        
        return False
    
    @staticmethod
    async def cancel_task(task_id: str, user_id: str) -> bool:
        """
        Cancela uma tarefa pendente.
        Só pode cancelar tarefas em status PENDING.
        """
        result = await db[TASK_LOG_COLLECTION].update_one(
            {
                "$or": [{"task_id": task_id}, {"id": task_id}],
                "user_id": user_id,
                "status": TaskStatus.PENDING.value
            },
            {
                "$set": {
                    "status": TaskStatus.CANCELLED.value,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "progress_message": "Cancelada pelo utilizador"
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"[TaskLog] Tarefa cancelada: {task_id}")
            return True
        
        return False
    
    @staticmethod
    async def mark_processing(task_id: str) -> Optional[TaskLogResponse]:
        """Marca uma tarefa como em processamento."""
        return await TaskLogService.update_task(
            task_id,
            status=TaskStatus.PROCESSING,
            progress_message="Iniciando processamento..."
        )
    
    @staticmethod
    async def mark_completed(
        task_id: str,
        result_url: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None
    ) -> Optional[TaskLogResponse]:
        """Marca uma tarefa como concluída com sucesso."""
        return await TaskLogService.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            progress_message="Concluído com sucesso!",
            result_url=result_url,
            result_data=result_data
        )
    
    @staticmethod
    async def mark_failed(task_id: str, error_message: str) -> Optional[TaskLogResponse]:
        """Marca uma tarefa como falhada."""
        return await TaskLogService.update_task(
            task_id,
            status=TaskStatus.FAILED,
            progress_message="Falha no processamento",
            error_message=error_message
        )
    
    @staticmethod
    async def update_progress(
        task_id: str,
        progress: int,
        progress_message: Optional[str] = None
    ) -> Optional[TaskLogResponse]:
        """Actualiza o progresso de uma tarefa."""
        return await TaskLogService.update_task(
            task_id,
            progress=progress,
            progress_message=progress_message
        )
    
    @staticmethod
    async def cleanup_old_tasks() -> int:
        """
        Remove tarefas antigas da base de dados.
        Deve ser chamado periodicamente por um cron job.
        
        Returns:
            Número de documentos removidos
        """
        now = datetime.now(timezone.utc)
        
        # Remover tarefas concluídas e confirmadas há mais de 24h
        acknowledged_cutoff = (now - timedelta(hours=COMPLETED_TASK_TTL_HOURS)).isoformat()
        
        # Remover tarefas concluídas não confirmadas há mais de 72h
        unacknowledged_cutoff = (now - timedelta(hours=UNACKNOWLEDGED_TASK_TTL_HOURS)).isoformat()
        
        result = await db[TASK_LOG_COLLECTION].delete_many({
            "status": {"$in": [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]},
            "$or": [
                {"acknowledged_at": {"$ne": None, "$lt": acknowledged_cutoff}},
                {
                    "acknowledged_at": None,
                    "completed_at": {"$lt": unacknowledged_cutoff}
                }
            ]
        })
        
        deleted_count = result.deleted_count
        if deleted_count > 0:
            logger.info(f"[TaskLog] Limpeza: {deleted_count} tarefas antigas removidas")
        
        return deleted_count


# Instância global do serviço
task_log_service = TaskLogService()
