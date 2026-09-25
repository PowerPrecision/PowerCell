"""Presença global: quem está online, visto por TODOS os workers.

LIMPEZA ESTRUTURAL, PONTO 2.

O DEFEITO
  O `ConnectionManager` guarda `active_connections` num dicionário EM
  MEMÓRIA. Com `UVICORN_WORKERS=2` (render.yaml) cada worker só conhece
  as suas ligações, e `is_user_connected` responde `False` sobre um
  utilizador que está online no worker vizinho.

  O custo não é cosmético. Em `realtime_notifications`:

      if manager.is_user_connected(user_id):   # memória LOCAL
          ...
      else:
          await send_push_notification(...)     # telemóvel

  Um utilizador com o socket no worker B, ao receber uma notificação
  emitida pelo worker A, levava um push no telemóvel **enquanto estava a
  olhar para a aplicação**. Ruído no bolso de quem está a trabalhar.

A ESTRUTURA: UM ZSET
  ``presenca:online`` — membro = ``user_id``, score = INSTANTE DE
  EXPIRAÇÃO (epoch em segundos).

    - está online?      ``ZSCORE`` > agora           → O(1)
    - quem está online? ``ZRANGEBYSCORE agora +inf`` → UMA chamada

  O lote é o que interessa: `chat_presence` e `chat_conversations`
  perguntavam `is_user_connected` DENTRO de um ciclo, um pedido por
  utilizador. Com o ZSET passam a uma leitura só — fica mais barato do
  que estava.

PORQUE É QUE NÃO SE REMOVE NA DESCONEXÃO
  Se o worker A removesse a entrada ao fechar o seu socket, o worker B —
  que ainda tem um separador aberto do mesmo utilizador — só a repunha
  no batimento seguinte. Nesse intervalo o utilizador apanhava push
  estando online, que é exactamente o defeito que isto vem corrigir.

  Deixando expirar, a entrada só morre quando NENHUM worker a renova.
  Zero fantasmas depois de um crash (o que um `SET` simples nunca
  resolve), ao preço de até `TTL` segundos de "online" a mais depois de
  o último separador fechar.

  Esse erro é para o lado seguro: push a MENOS, e a notificação fica na
  base de dados à espera. O erro inverso — push a mais — é o que temos
  hoje.

O BATIMENTO JÁ EXISTE
  O `useWebSocket` manda `ping` de 30 em 30s e o
  `websocket_api_notifications` já o trata. É aí que se renova. Sem
  temporizador novo, sem tarefa de fundo.

DEGRADAÇÃO: RECAI NA MEMÓRIA LOCAL
  Redis em baixo → responde o `ConnectionManager` do processo, que é o
  comportamento de hoje.

  Aqui a degradação é ABERTA e não fechada, ao contrário da regra que
  sigo no isolamento por rede e no Explorador de ficheiros. A razão é
  que presença NÃO é fronteira de segurança: nenhum dado muda de dono
  por causa dela. Uma leitura falhada que respondesse "ninguém está
  online" partia o Chat e enchia telemóveis de push. **Não "corrigir"
  isto para fail-closed.**
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

logger = logging.getLogger(__name__)

# Chave única. Um ZSET só, e não uma chave por utilizador: é o que
# permite responder "quem está online" numa chamada em vez de um SCAN.
CHAVE_PRESENCA = "presenca:online"

# 3× o batimento de 30s do `useWebSocket`: tolera um ping perdido sem
# declarar o utilizador offline. Subir isto aumenta o rasto de "online"
# depois de fechar; descer aproxima-o de um falso offline por soluço de
# rede, que é o erro caro.
TTL_SEGUNDOS = 90


def _agora() -> float:
    """Relógio de PAREDE (não monotónico) de propósito.

    O score é partilhado entre processos e entre máquinas; um relógio
    monotónico tem origem arbitrária por processo e os scores de dois
    workers não seriam comparáveis.
    """
    return time.time()


async def _cliente():
    """Cliente Redis partilhado com o Pub/Sub. Nunca levanta.

    Reutiliza `redis_pubsub._get_publisher` de propósito: é UMA
    infra-estrutura Redis, com um circuit breaker já implementado e
    testado. Abrir uma segunda ligação duplicaria a gestão de falhas.
    """
    try:
        from services.redis_pubsub import _get_publisher

        return await _get_publisher()
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.debug(f"[PRESENCA] Redis indisponível: {e}")
        return None


def _local_online(user_id: str) -> bool:
    """A resposta do `ConnectionManager` deste processo (o recurso)."""
    try:
        from services.websocket_manager import manager

        return manager.is_user_connected(user_id)
    except Exception:  # pragma: no cover
        return False


def _local_todos() -> set[str]:
    try:
        from services.websocket_manager import manager

        return set(manager.get_connected_users())
    except Exception:  # pragma: no cover
        return set()


# ====================================================================
# ESCRITA
# ====================================================================

async def marcar_online(user_id: str) -> bool:
    """Renova a presença de ``user_id`` por mais ``TTL_SEGUNDOS``.

    Chamada na ligação e a cada `ping`. Devolve `True` se chegou ao
    Redis — o chamador não precisa de saber, mas os testes precisam.
    """
    if not user_id:
        return False
    cliente = await _cliente()
    if cliente is None:
        return False
    try:
        await cliente.zadd(CHAVE_PRESENCA, {user_id: _agora() + TTL_SEGUNDOS})
        return True
    except Exception as e:
        logger.warning(f"[PRESENCA] Falha a marcar {user_id} online: {e}")
        return False


async def limpar_expirados() -> int:
    """Remove do ZSET quem já expirou. Devolve quantos saíram.

    As leituras já filtram por score, portanto isto é HIGIENE e não
    correcção: sem ele o ZSET cresceria com todos os utilizadores que
    alguma vez se ligaram.
    """
    cliente = await _cliente()
    if cliente is None:
        return 0
    try:
        return int(await cliente.zremrangebyscore(CHAVE_PRESENCA, "-inf", _agora()))
    except Exception as e:  # pragma: no cover
        logger.debug(f"[PRESENCA] Falha a limpar expirados: {e}")
        return 0


# ====================================================================
# LEITURA
# ====================================================================

async def esta_online(user_id: str) -> bool:
    """``user_id`` tem sessão aberta em ALGUM worker?

    Sem Redis, responde o `ConnectionManager` deste processo — que é a
    resposta de hoje, e é melhor do que não responder.
    """
    if not user_id:
        return False
    cliente = await _cliente()
    if cliente is None:
        return _local_online(user_id)
    try:
        score = await cliente.zscore(CHAVE_PRESENCA, user_id)
    except Exception as e:
        logger.warning(f"[PRESENCA] Falha a ler {user_id} — recurso local: {e}")
        return _local_online(user_id)
    if score is None:
        # Ainda assim consulta o local: uma ligação acabada de abrir
        # neste worker pode não ter chegado ao Redis (escrita falhada),
        # e dizer "offline" mandava um push a quem está mesmo online.
        return _local_online(user_id)
    return float(score) > _agora()


async def online_entre(user_ids: Iterable[str]) -> set[str]:
    """Quais destes estão online. UMA chamada ao Redis, não N.

    É o ponto todo do ZSET: `chat_presence` e `chat_conversations`
    perguntavam um a um dentro de um ciclo.
    """
    pedidos = {u for u in user_ids if u}
    if not pedidos:
        return set()
    cliente = await _cliente()
    if cliente is None:
        return pedidos & _local_todos()
    try:
        vivos = await cliente.zrangebyscore(CHAVE_PRESENCA, _agora(), "+inf")
    except Exception as e:
        logger.warning(f"[PRESENCA] Falha a ler o conjunto — recurso local: {e}")
        return pedidos & _local_todos()
    # A união com o local cobre o mesmo caso do `esta_online`: quem está
    # ligado AQUI e ainda não chegou ao Redis.
    return (pedidos & set(vivos)) | (pedidos & _local_todos())


async def todos_online() -> set[str]:
    """Todos os utilizadores com sessão aberta, em qualquer worker."""
    cliente = await _cliente()
    if cliente is None:
        return _local_todos()
    try:
        vivos = await cliente.zrangebyscore(CHAVE_PRESENCA, _agora(), "+inf")
    except Exception as e:
        logger.warning(f"[PRESENCA] Falha a listar — recurso local: {e}")
        return _local_todos()
    return set(vivos) | _local_todos()
