"""Deltas de processo em tempo real (Kanban / realtime).

Extraído de `routes/processes.py`.

ÉPICO 10, FASE 2 — o que aqui mudou, e porquê
=============================================
Esta função fazia ``manager.broadcast()`` e a sua própria docstring dizia
"*to all connected WebSocket clients*". O delta transporta ``client_name`` e
``process_number``: um processo criado na Power inseria um cartão, com o nome
do cliente, no Kanban de quem estivesse ligado na **Domus** — e ainda disparava
um toast com esse nome. O isolamento do Lote 4/5 vive todo nas *queries*, e o
WebSocket não faz query nenhuma; foi por aí que a fuga passou.

Hoje o delta é endereçado à **audiência do processo**
(``services/realtime_audience.py``), resolvida a partir do documento que o
emissor já tem em mãos. Por isso o parâmetro ``process`` é obrigatório na
prática: sem ele não há audiência, o transporte recusa o envelope e **não se
entrega nada**. Falha fechada — um chamador distraído produz silêncio, nunca
uma difusão geral.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.realtime_delivery import entregar_a_processo

logger = logging.getLogger(__name__)


def build_process_delta_payload(
    *,
    process_id: str,
    process_number: Any = None,
    client_name: Optional[str] = None,
    status: Optional[str] = None,
    old_status: Optional[str] = None,
    assigned_consultor_ids: Optional[list] = None,
    assigned_mediador_ids: Optional[list] = None,
    consultor_names: Optional[list] = None,
    mediador_names: Optional[list] = None,
    priority: Optional[str] = None,
    prioridade: Optional[str] = None,
    process_type: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Monta o payload leve (só campos non-None)."""
    delta: dict[str, Any] = {"process_id": process_id}
    optional = {
        "process_number": process_number,
        "client_name": client_name,
        "status": status,
        "old_status": old_status,
        "assigned_consultor_ids": assigned_consultor_ids,
        "assigned_mediador_ids": assigned_mediador_ids,
        "consultor_names": consultor_names,
        "mediador_names": mediador_names,
        "priority": priority,
        "prioridade": prioridade,
        "process_type": process_type,
        "updated_at": updated_at,
    }
    for key, value in optional.items():
        if value is not None:
            delta[key] = value
    return delta


async def broadcast_process_delta(
    event_type: str,
    process_id: str,
    process_number: int = None,
    client_name: str = None,
    status: str = None,
    old_status: str = None,
    assigned_consultor_ids: list = None,
    assigned_mediador_ids: list = None,
    consultor_names: list = None,
    mediador_names: list = None,
    priority: str = None,
    prioridade: str = None,
    process_type: str = None,
    updated_at: str = None,
    process: dict = None,
    tambem_para: list = None,
) -> None:
    """Entrega um delta leve a quem tem direito a ver este processo.

    Args:
        process: O documento do processo, de onde sai a audiência (carimbo
            de rede/empresa + atribuições). **Sem ele não há entrega**: um
            delta sem audiência seria um broadcast, que é precisamente o
            defeito que este módulo deixou de ter.
    """
    try:
        delta = build_process_delta_payload(
            process_id=process_id,
            process_number=process_number,
            client_name=client_name,
            status=status,
            old_status=old_status,
            assigned_consultor_ids=assigned_consultor_ids,
            assigned_mediador_ids=assigned_mediador_ids,
            consultor_names=consultor_names,
            mediador_names=mediador_names,
            priority=priority,
            prioridade=prioridade,
            process_type=process_type,
            updated_at=updated_at,
        )
        if not process:
            logger.warning(
                "[RT] Delta '%s' do processo %s sem documento de origem — "
                "não entregue (sem audiência não há difusão)",
                event_type, process_id,
            )
            return
        await entregar_a_processo(
            process, event_type, delta, tambem_para=tambem_para or ()
        )
        logger.debug(f"Delta {event_type} entregue à audiência de {process_id}")
    except Exception as e:
        logger.error(f"Error broadcasting process delta: {e}")
