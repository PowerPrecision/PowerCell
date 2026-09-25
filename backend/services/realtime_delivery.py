"""Ponto ÚNICO de entrega de eventos em tempo real (Épico 10, Fase 1).

O PROBLEMA QUE FECHA
====================
O tempo real tinha duas condutas. O Épico 4 (`task_*`) e o Épico 5
(`new_email`) passaram pelo Redis; os outros **33 pontos de emissão, em 12
módulos**, continuaram a escrever directamente no `ConnectionManager` em
memória. Com `UVICORN_WORKERS=2` (render.yaml), um evento emitido no worker A
para um socket no worker B simplesmente não chega — e não dá erro nenhum.

Este módulo é a conduta única. Quem emite um evento chama uma destas funções
e nunca `manager.*`: é a regra que impede a falésia de voltar por um ponto
novo. A guarda `tests/unit/test_realtime_delivery.py` afirma isso sobre o
código-fonte dos emissores.

TRÊS FORMAS DE ENDEREÇO — E NENHUMA É "TODA A GENTE"
====================================================
* ``entregar_a_utilizador`` — o destinatário é um e é conhecido.
* ``entregar_a_processo`` / ``entregar_a_audiencia`` — o evento diz respeito
  a quem tem direito a ver aquele processo, sem os enumerar (Fase 2).
* ``entregar_na_sala`` — quem está naquele ecrã. A autorização foi feita à
  ENTRADA da sala; aqui só falta atravessar a fronteira do worker.

DEGRADAÇÃO GRACIOSA
===================
Nenhuma destas funções levanta. Um evento perdido degrada a UI para polling;
nunca pode fazer falhar a operação de negócio que o originou. É a mesma
regra do `publish_event`, e é por isso que o resultado booleano é
informativo e não precisa de ser tratado pelo chamador.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.realtime_audience import (
    Audiencia,
    audiencia_das_redes_do_utilizador,
    audiencia_do_processo,
)
from services.redis_pubsub import publish_event

logger = logging.getLogger(__name__)


async def entregar_a_utilizador(
    user_id: str,
    event_type: str,
    payload: dict,
    *,
    company_id: Optional[str] = None,
) -> bool:
    """Entrega a UM destinatário conhecido, em qualquer worker."""
    if not user_id:
        logger.warning(
            "[RT] '%s' sem destinatário — descartado (nunca difundido)",
            event_type,
        )
        return False
    return await publish_event(
        event_type, payload or {}, user_id=str(user_id), company_id=company_id
    )


async def entregar_a_audiencia(
    audiencia: Audiencia,
    event_type: str,
    payload: dict,
) -> bool:
    """Entrega a quem a audiência alcançar — sem enumerar destinatários.

    Uma audiência sem alcance é recusada pelo transporte: não existe aqui
    caminho nenhum que degrade para difusão geral.
    """
    return await publish_event(event_type, payload or {}, audiencia=audiencia)


async def entregar_a_processo(
    process: dict,
    event_type: str,
    payload: dict,
    *,
    tambem_para: Any = (),
) -> bool:
    """Atalho para o caso mais comum: o evento é sobre um processo.

    A audiência sai do documento que o emissor JÁ tem em mãos — zero
    queries. Um processo sem carimbo de rede cai na pilha por carimbar e só
    alcança quem inclui a rede de omissão (a mesma regra da listagem).
    """
    return await entregar_a_audiencia(
        audiencia_do_processo(process or {}, tambem_para=tambem_para or ()),
        event_type,
        payload,
    )


async def entregar_na_sala(
    room: str,
    event_type: str,
    payload: dict,
    *,
    exclude_user_id: Optional[str] = None,
) -> bool:
    """Entrega a quem está na sala, em qualquer worker."""
    if not room:
        logger.warning("[RT] '%s' sem sala — descartado", event_type)
        return False
    return await publish_event(
        event_type,
        payload or {},
        room=str(room),
        exclude_user_id=exclude_user_id or None,
    )


async def entregar_as_redes(scope, event_type: str, payload: dict) -> bool:
    """Entrega a toda a gente das redes deste utilizador (presença).

    Sem rede resolvida não se emite nada: um evento de presença sem
    fronteira voltaria a ser o broadcast que este Épico fechou.
    """
    entregue = False
    for audiencia in audiencia_das_redes_do_utilizador(scope):
        if await entregar_a_audiencia(audiencia, event_type, payload):
            entregue = True
    return entregue


def sala_do_processo(process_id: Any) -> str:
    """Nome canónico da sala de um processo. Um sítio só, para não divergir."""
    return f"process_{process_id}"
