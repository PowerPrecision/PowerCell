"""Task logs detail/action handlers.

Extraído de `routes/task_logs.py`.
Do **not** overwrite services/task_log_service.py.

FRONTEIRA DE REDE (Out 2026, D-31)
==================================
Um registo de tarefa assíncrona é do utilizador que a lançou, e leva o
`process_name` (o nome do cliente) e os `metadata`. O acesso por id tinha
duas falhas:

* **admin/ceo atravessavam redes.** A excepção era `role in ["master",
  "admin", "ceo"]` — o cargo da conta, sem pergunta de rede. Desde a adenda
  de RBAC Admin e CEO são perfis LOCAIS: o CEO da Domus lia, cancelava e
  apagava os registos da Power bastando saber o id;
* **o 403 confirmava o id.** «Acesso não autorizado» para quem não é dono
  distinguia «existe e não é teu» de «não existe».

Hoje (`_carregar_acessivel`): o dono vê sempre o seu; o Master vê tudo;
Admin/CEO só os de utilizadores do seu âmbito (a mesma pergunta da gestão
de utilizadores, `carregar_utilizador_gerivel`); para todos os outros —
e para tudo o que está fora do âmbito — a resposta é o **404** de «não
existe».
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from database import db
from models.task_log import TaskStatus
from services.role_scope import utilizador_e_global
from services.task_log_service import task_log_service

logger = logging.getLogger(__name__)

ERRO_TAREFA_NAO_ENCONTRADA = "Tarefa não encontrada"

#: Perfis (cargo da conta) que podem consultar registos de OUTROS — mas só
#: os de utilizadores do seu âmbito. Master não está aqui: não tem fronteira.
PAPEIS_QUE_VEEM_OS_DOS_OUTROS = frozenset({"admin", "ceo"})


async def _carregar_acessivel(task_id: str, user: dict, *, so_o_dono: bool = False):
    """O registo, se quem pede lhe pode tocar. **404** caso contrário."""
    task = await task_log_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=ERRO_TAREFA_NAO_ENCONTRADA)

    user = user or {}
    if task.user_id == user.get("id"):
        return task
    if so_o_dono:
        raise HTTPException(status_code=404, detail=ERRO_TAREFA_NAO_ENCONTRADA)
    if utilizador_e_global(user):
        return task
    if str(user.get("role") or "").lower() in PAPEIS_QUE_VEEM_OS_DOS_OUTROS:
        from services.user_management_scope import carregar_utilizador_gerivel

        try:
            await carregar_utilizador_gerivel(task.user_id, user)
            return task
        except HTTPException:
            # Dono fora do âmbito (ou que já não existe): igual a «não existe».
            pass

    logger.warning(
        "[TASK-LOGS] %s pediu o registo %s, que não é seu nem do seu âmbito.",
        user.get("id"), task_id,
    )
    raise HTTPException(status_code=404, detail=ERRO_TAREFA_NAO_ENCONTRADA)


async def run_get_task_details(task_id: str, user: dict):
    return await _carregar_acessivel(task_id, user)


async def run_acknowledge_task(task_id: str, user: dict):
    # Confirmar que se viu é do dono e de mais ninguém (nem do Master).
    await _carregar_acessivel(task_id, user, so_o_dono=True)

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


async def run_cancel_task(task_id: str, user: dict):
    task = await _carregar_acessivel(task_id, user)

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


async def run_delete_task(task_id: str, user: dict):
    task = await _carregar_acessivel(task_id, user)

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
