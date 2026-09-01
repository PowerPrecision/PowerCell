"""Staff task CRUD (create / list / get / update / complete / reopen / delete).

Extraído de `routes/tasks.py`. Uses `task_api_*` to avoid colliding with
`task_queue.py` / `task_log_service.py`.
"""
from __future__ import annotations

import logging
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException

from database import db
from models.task import TaskCreate, TaskUpdate, TaskResponse
from services.history import log_history
from services.realtime_notifications import send_realtime_notification
from utils.input_sanitization import sanitize_string
from services.task_api_helpers import _block_parceiro, enrich_task

logger = logging.getLogger(__name__)


async def run_create_task(task_data: TaskCreate, current_user: dict):
    """
    Criar nova tarefa.
    Qualquer utilizador pode criar tarefas e atribuir a qualquer pessoa.
    """
    _block_parceiro(current_user)
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Sanitizar inputs do utilizador antes de guardar
    sanitized_title = sanitize_string(task_data.title, max_length=300) if task_data.title else task_data.title
    sanitized_description = sanitize_string(task_data.description, max_length=2000) if task_data.description else task_data.description

    # Construir título com referência do processo + nome do processo se aplicável
    # REGRA DE NOMENCLATURA (Pacote M, Fix #2):
    # Sempre que a tarefa estiver associada a um process_id, o título final
    # gravado na BD deve incluir a referência do processo (process_ref, ex:
    # "PROC-012") como prefixo, no formato:  [PROC-012] Título original
    # Se o título original já contiver "[PROC-" (case-insensitive), ignora
    # para evitar duplicação.
    title = sanitized_title or task_data.title
    process_name = None

    if task_data.process_id:
        process = await db.processes.find_one(
            {"id": task_data.process_id},
            {"_id": 0, "client_name": 1, "process_ref": 1, "process_number": 1}
        )
        if process:
            process_name = process.get("client_name", "")
            # ── Prefixar com a referência do processo ([PROC-012]) ──
            # Preferir process_ref (formato canónico "PROC-012"); fazer fallback
            # para process_number formatado; nunca gerar prefixo vazio.
            process_ref = process.get("process_ref")
            if not process_ref and process.get("process_number") is not None:
                try:
                    process_ref = f"PROC-{int(process['process_number']):04d}"
                except (ValueError, TypeError):
                    process_ref = None

            if process_ref:
                # Evitar duplicação: se o título já contém [PROC-..., saltar
                # (comparação case-insensitive para cobrir [proc-012] digitado manualmente)
                title_lower = (title or "").lower()
                if "[proc-" not in title_lower:
                    title = f"[{process_ref}] {title or ''}".rstrip()
            # ── Manter comportamento legado: adicionar nome do cliente se ausente ──
            if process_name and process_name not in (title or ""):
                title = f"[{process_name}] {title or ''}".rstrip()

    task = {
        "id": task_id,
        "title": title,
        "description": sanitized_description,
        "assigned_to": task_data.assigned_to,
        "process_id": task_data.process_id,
        "due_date": task_data.due_date,  # Data de vencimento (opcional)
        "priority": task_data.priority,  # "Alta"/"Média"/"Baixa" (opcional)
        "created_by": current_user["id"],
        "completed": False,
        "completed_at": None,
        "completed_by": None,
        "created_at": now,
        "updated_at": now
    }

    await db.tasks.insert_one(task)
    logger.info(f"Tarefa criada: {task_id} por {current_user['name']}")

    # ── Audit Trail ──
    if task_data.process_id:
        await log_history(task_data.process_id, current_user, "Criou tarefa", "tarefa", None, title)

    # Enviar notificações para os utilizadores atribuídos
    due_info = ""
    if task_data.due_date:
        try:
            due = datetime.fromisoformat(task_data.due_date.replace("Z", "+00:00"))
            due_info = f" (vence {due.strftime('%d/%m/%Y')})"
        except (ValueError, TypeError):
            pass

    for user_id in task_data.assigned_to:
        if user_id != current_user["id"]:  # Não notificar o criador
            await send_realtime_notification(
                user_id=user_id,
                title="📋 Nova Tarefa Atribuída",
                message=f"{current_user['name']} atribuiu-lhe uma tarefa: {title}{due_info}",
                notification_type="task_assigned",
                link="/tasks" if not task_data.process_id else f"/process/{task_data.process_id}",
                process_id=task_data.process_id
            )

    # Retornar tarefa enriquecida
    enriched = await enrich_task(task)
    return TaskResponse(**enriched)


async def run_get_tasks(
    current_user: dict,
    *,
    process_id: Optional[str] = None,
    user_id: Optional[str] = None,
    assigned_to_me: bool = False,
    created_by_me: bool = False,
    include_completed: bool = False,
):
    """
    Listar tarefas.

    Filtros:
    - process_id: Filtrar por processo específico
    - user_id: Filtrar por utilizador específico ou 'all' para todos (apenas admin/ceo)
    - assigned_to_me: Apenas tarefas atribuídas ao utilizador atual
    - created_by_me: Apenas tarefas criadas pelo utilizador atual
    - include_completed: Incluir tarefas já concluídas

    Calendário Global (admin/ceo):
    - Se user_id='all', retorna tarefas de toda a equipa
    - Se user_id=<id_especifico>, retorna tarefas desse utilizador
    """
    _block_parceiro(current_user)
    query = {}

    # Verificar se é admin/ceo para acesso global
    is_admin_or_ceo = current_user.get("role") in ["admin", "ceo", "diretor"]

    # Filtro por processo
    if process_id:
        query["process_id"] = process_id

    # Filtro por user_id (calendário global para admin/ceo)
    if user_id:
        if user_id.lower() == "all":
            if not is_admin_or_ceo:
                raise HTTPException(
                    status_code=403,
                    detail="Apenas administradores podem ver tarefas de todos os utilizadores"
                )
            # Não adicionar filtro - retorna todas as tarefas
            logger.info(f"Calendário global: {current_user['email']} a aceder a todas as tarefas")
        else:
            # Filtrar por utilizador específico
            if not is_admin_or_ceo and user_id != current_user["id"]:
                raise HTTPException(
                    status_code=403,
                    detail="Não tem permissão para ver tarefas de outros utilizadores"
                )
            query["assigned_to"] = user_id

    # Filtro por atribuição (próprio utilizador)
    elif assigned_to_me:
        query["assigned_to"] = current_user["id"]

    # Filtro por criador
    if created_by_me:
        query["created_by"] = current_user["id"]

    # Filtro por estado
    if not include_completed:
        query["completed"] = False

    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)

    # Enriquecer tarefas com nomes
    enriched_tasks = []
    for task in tasks:
        enriched = await enrich_task(task)
        enriched_tasks.append(TaskResponse(**enriched))

    return enriched_tasks


async def run_get_my_tasks(current_user: dict, *, include_completed: bool = False):
    """
    Listar tarefas atribuídas ao utilizador atual.
    """
    _block_parceiro(current_user)
    query = {
        "assigned_to": current_user["id"]
    }

    if not include_completed:
        query["completed"] = False

    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    enriched_tasks = []
    for task in tasks:
        enriched = await enrich_task(task)
        enriched_tasks.append(TaskResponse(**enriched))

    return enriched_tasks


async def run_get_task(task_id: str, current_user: dict):
    """Obter detalhes de uma tarefa."""
    _block_parceiro(current_user)
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    enriched = await enrich_task(task)
    return TaskResponse(**enriched)


async def run_update_task(task_id: str, task_data: TaskUpdate, current_user: dict):
    """Actualizar uma tarefa."""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if task_data.title is not None:
        update_data["title"] = sanitize_string(task_data.title, max_length=300) if task_data.title else task_data.title
    if task_data.description is not None:
        update_data["description"] = sanitize_string(task_data.description, max_length=2000) if task_data.description else task_data.description
    if task_data.assigned_to is not None:
        update_data["assigned_to"] = task_data.assigned_to
        # Notificar novos utilizadores
        new_assignees = set(task_data.assigned_to) - set(task.get("assigned_to", []))
        for user_id in new_assignees:
            if user_id != current_user["id"]:
                await send_realtime_notification(
                    user_id=user_id,
                    title="📋 Nova Tarefa Atribuída",
                    message=f"{current_user['name']} atribuiu-lhe uma tarefa: {task['title']}",
                    notification_type="task_assigned",
                    link="/tasks" if not task.get("process_id") else f"/process/{task['process_id']}",
                    process_id=task.get("process_id")
                )

    await db.tasks.update_one({"id": task_id}, {"$set": update_data})

    # ── Audit Trail ──
    if task.get("process_id"):
        await log_history(task["process_id"], current_user, "Atualizou tarefa", "tarefa", task.get("title"), update_data.get("title") or task.get("title"))

    updated_task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    enriched = await enrich_task(updated_task)
    return TaskResponse(**enriched)


async def run_complete_task(task_id: str, current_user: dict):
    """Marcar tarefa como concluída."""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    now = datetime.now(timezone.utc).isoformat()

    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {
            "completed": True,
            "completed_at": now,
            "completed_by": current_user["id"],
            "updated_at": now
        }}
    )

    logger.info(f"Tarefa {task_id} marcada como concluída por {current_user['name']}")

    # ── Audit Trail ──
    if task.get("process_id"):
        await log_history(task["process_id"], current_user, "Concluiu tarefa", "tarefa", None, task.get("title"))

    # Notificar o criador se for diferente de quem concluiu
    if task["created_by"] != current_user["id"]:
        await send_realtime_notification(
            user_id=task["created_by"],
            title="✅ Tarefa Concluída",
            message=f"{current_user['name']} concluiu a tarefa: {task['title']}",
            notification_type="task_completed",
            link="/tasks" if not task.get("process_id") else f"/process/{task['process_id']}",
            process_id=task.get("process_id")
        )

    updated_task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    enriched = await enrich_task(updated_task)
    return TaskResponse(**enriched)


async def run_reopen_task(task_id: str, current_user: dict):
    """Reabrir tarefa concluída."""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {
            "completed": False,
            "completed_at": None,
            "completed_by": None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    # ── Audit Trail ──
    if task.get("process_id"):
        await log_history(task["process_id"], current_user, "Reabriu tarefa", "tarefa", None, task.get("title"))

    updated_task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    enriched = await enrich_task(updated_task)
    return TaskResponse(**enriched)


async def run_delete_task(task_id: str, current_user: dict):
    """Eliminar tarefa."""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})

    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    # Apenas o criador ou admin pode eliminar
    if task["created_by"] != current_user["id"] and current_user["role"] not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Sem permissão para eliminar esta tarefa")

    await db.tasks.delete_one({"id": task_id})
    logger.info(f"Tarefa {task_id} eliminada por {current_user['name']}")

    # ── Audit Trail ──
    if task.get("process_id"):
        await log_history(task["process_id"], current_user, "Eliminou tarefa", "tarefa", task.get("title"), None)

    return {"success": True, "message": "Tarefa eliminada"}
