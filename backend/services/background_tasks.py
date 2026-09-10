"""Registry de tarefas background fire-and-forget.

BUGFIX (E2E — email de boas-vindas, Set 2026): o asyncio apenas mantém
referências FRACAS às corotinas lançadas com `asyncio.create_task` — sem
uma referência forte, a task pode ser recolhida pelo garbage collector a
meio da execução (comportamento documentado na docs oficiais do Python,
secção "create_task": "Save a reference to the result of this function,
to avoid a task disappearing mid-execution").

Vários fluxos críticos (email de boas-vindas do Portal, gatilhos de
onboarding pós-upload) usavam `asyncio.create_task(...)` puro sem guardar
referência — em janelas de GC podiam desaparecer antes de enviar o email.

Uso canónico:

    from services.background_tasks import spawn_background_task

    spawn_background_task(send_portal_welcome_email_from_process(...), name="portal-welcome-email")
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Referências fortes às tasks em curso (limpas automaticamente em conclusão)
_background_tasks: set[asyncio.Task] = set()


def spawn_background_task(
    coro,
    *,
    name: Optional[str] = None,
) -> asyncio.Task:
    """
    Lança uma corotina em background garantindo referência forte.

    Args:
        coro: corotina a executar (asyncio.create_task consome-a).
        name: nome opcional para diagnóstico (asyncio.Task name).

    Returns:
        A task criada (já agendada no event loop).
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def pending_background_tasks() -> int:
    """Número de tarefas background registadas e ainda em curso."""
    return len(_background_tasks)
