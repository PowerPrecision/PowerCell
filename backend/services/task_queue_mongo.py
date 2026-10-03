"""
====================================================================
A FILA DE TAREFAS DO WORKER — A QUE O CÓDIGO JÁ DIZIA QUE EXISTIA
====================================================================
Lote 2, ponto 1.

O DEFEITO
  `worker.py` chama QUATRO métodos que não existem em sítio nenhum:

      task_queue.get_next_task()                 worker_loop, a cada ciclo
      task_queue.complete_task(id, result=…)     fim de cada tarefa
      task_queue.fail_task(id, error=…)          falha de cada tarefa
      task_queue.add_task("match_leads", {})     scheduler_loop, 30 min

  `TaskQueueService` é ARQ/Redis e tem `enqueue`, `send_email`,
  `process_document`, `health_check` e `get_job_status`. Não tem
  `__getattr__`. Logo cada uma daquelas chamadas levanta
  `AttributeError`.

  CONSEQUÊNCIA EXACTA, que é pior do que parece:

  1. `worker_loop` rebenta no `get_next_task()` a cada **5 segundos**,
     desde sempre. O `except Exception` loga e volta a tentar. O
     despachante `process_task` (scrape de imóveis, matching, email)
     **nunca correu uma única vez**.

  2. No `scheduler_loop`, o `add_task` está DENTRO do
     `async with heartbeat("lead_matching")`. A excepção sobe, o
     batimento marca `erro` e re-levanta — e a subida salta o resto do
     ciclo. O bloco de sincronização de webmail está DEPOIS, logo
     **nunca era alcançado**: é essa a razão de `webmail_worker_sync`
     aparecer como «Nunca correu» no painel, e não um worker morto.

     O sintoma reportado apontava para "o Processador está em baixo"; a
     causa é uma linha inalcançável por uma excepção lançada três linhas
     acima. Os dois estados do painel diziam a verdade e nenhum deles
     dizia isto.

A IRONIA DOCUMENTADA
  A docstring do `client_portal_email.py` afirma, a explicar outro
  bugfix, que «o worker de produção arranca com `python worker.py` (loop
  próprio que processa a fila Mongo por `task_type`)». A fila Mongo que
  essa frase descreve **nunca foi escrita**. A crença estava registada
  em dois sítios e era falsa nos dois — e nenhum deles verificou se o
  método existia.

PORQUE MONGO E NÃO ARQ
  O `enqueue` do ARQ funciona (há Redis Upstash) mas **não há
  consumidor**: o `arq worker.config.WorkerSettings` nunca é lançado.
  Uma fila com produtor e sem consumidor aceita tudo e entrega nada —
  foi exactamente assim que o email de boas-vindas do Portal morreu em
  silêncio. Mongo é o que os dois processos vêem, é o que o `worker.py`
  já esperava, e é inspeccionável quando alguém pergunta "onde ficou a
  minha tarefa?".

TRÊS DECISÕES QUE NÃO SE PODEM PERDER
  1. **`disponivel_em` (backoff) não é luxo.** O `worker_loop` só dorme
     quando NÃO há tarefa. Uma tarefa que falhe sempre e volte logo a
     `pendente` punha o laço a girar a 100% de CPU — a correcção teria
     trocado um worker parado por um worker a arder. A reentrada é
     adiada, e o adiamento cresce com as tentativas.
  2. **A reclamação é ATÓMICA** (`find_one_and_update`). Dois
     consumidores — ou o mesmo depois de um reinício — não podem
     apanhar a mesma tarefa.
  3. **Uma tarefa reclamada e nunca terminada volta à fila.** Um deploy
     a meio de uma tarefa deixa-a `a_processar` para sempre; sem a
     recuperação ficava perdida sem erro nenhum. A recuperação corre no
     caminho da própria leitura, para não precisar de um laço novo que
     também pudesse estar em baixo.
====================================================================
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from database import db

logger = logging.getLogger(__name__)

COLECCAO = "task_queue"

ESTADO_PENDENTE = "pendente"
ESTADO_A_PROCESSAR = "a_processar"
ESTADO_CONCLUIDA = "concluida"
ESTADO_FALHADA = "falhada"

# Tentativas antes de desistir. Uma tarefa envenenada não pode ficar a
# voltar para sempre — fica `falhada` e visível.
MAX_TENTATIVAS = 3

# Espera antes de reentrar na fila, por número de tentativas já feitas.
# É isto que impede o `worker_loop` de girar a 100% sobre uma tarefa que
# falha sempre.
SEGUNDOS_DE_ESPERA_POR_TENTATIVA: tuple[int, ...] = (60, 300, 900)

# Uma tarefa reclamada há mais do que isto perdeu o consumidor (deploy,
# OOM, SIGKILL) e volta à fila.
SEGUNDOS_ATE_CONSIDERAR_PERDIDA = 1800


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.isoformat()


def espera_da_tentativa(tentativas_feitas: int) -> int:
    """Segundos de espera antes da próxima tentativa."""
    if tentativas_feitas <= 0:
        return SEGUNDOS_DE_ESPERA_POR_TENTATIVA[0]
    indice = min(tentativas_feitas - 1, len(SEGUNDOS_DE_ESPERA_POR_TENTATIVA) - 1)
    return SEGUNDOS_DE_ESPERA_POR_TENTATIVA[indice]


def construir_tarefa(
    task_type: str,
    payload: Optional[dict] = None,
    *,
    max_tentativas: int = MAX_TENTATIVAS,
) -> dict:
    """O documento de uma tarefa nova (puro, para poder ser afirmado em teste)."""
    agora = _agora()
    return {
        "id": str(uuid.uuid4()),
        "type": task_type,
        "payload": payload or {},
        "status": ESTADO_PENDENTE,
        "tentativas": 0,
        "max_tentativas": max(1, int(max_tentativas or 1)),
        "disponivel_em": _iso(agora),
        "created_at": _iso(agora),
        "updated_at": _iso(agora),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }


async def add_task(
    task_type: str,
    payload: Optional[dict] = None,
    *,
    max_tentativas: int = MAX_TENTATIVAS,
) -> Optional[str]:
    """Põe uma tarefa na fila. Devolve o id, ou ``None`` se não conseguiu.

    Nunca levanta: quem enfileira está, por norma, a tratar de outra
    coisa, e uma fila em baixo não pode derrubar o pedido que a usou.
    """
    tarefa = construir_tarefa(task_type, payload, max_tentativas=max_tentativas)
    try:
        await db[COLECCAO].insert_one(dict(tarefa))
    except Exception as e:
        logger.warning("[FILA] Não foi possível enfileirar %s: %s", task_type, e)
        return None
    logger.info("[FILA] Tarefa %s (%s) enfileirada", tarefa["id"], task_type)
    return tarefa["id"]


async def recuperar_tarefas_perdidas() -> int:
    """Devolve à fila as tarefas reclamadas que ninguém terminou.

    Corre no caminho da leitura de propósito: um laço próprio para isto
    seria mais uma coisa que pode estar em baixo precisamente quando é
    necessária.
    """
    limite = _iso(_agora() - timedelta(seconds=SEGUNDOS_ATE_CONSIDERAR_PERDIDA))
    try:
        resultado = await db[COLECCAO].update_many(
            {"status": ESTADO_A_PROCESSAR, "started_at": {"$lt": limite}},
            {"$set": {"status": ESTADO_PENDENTE, "updated_at": _iso(_agora())}},
        )
    except Exception as e:
        logger.warning("[FILA] Falha a recuperar tarefas perdidas: %s", e)
        return 0
    recuperadas = getattr(resultado, "modified_count", 0) or 0
    if recuperadas:
        logger.warning("[FILA] %s tarefa(s) sem consumidor devolvidas à fila", recuperadas)
    return recuperadas


async def get_next_task(
    *,
    tipos: Optional[Iterable[str]] = None,
    excluir_tipos: Optional[Iterable[str]] = None,
) -> Optional[dict]:
    """Reclama a próxima tarefa pendente, ou ``None``.

    A reclamação é ATÓMICA: o estado muda na mesma operação que a
    escolhe, logo dois consumidores não podem apanhar a mesma.

    `tipos` / `excluir_tipos` existem porque há **dois** consumidores no
    processo worker — o `worker_loop` (que despacha `scrape_property`,
    `match_leads`, `send_email`) e o `scheduler_loop` (que atende os
    pedidos de execução forçada). Sem o filtro, cada um reclamava tarefas
    que não sabe tratar e gastava-lhes as tentativas: um consumidor a
    roubar trabalho ao outro, e a tarefa a morrer `falhada` sem nunca ter
    chegado a quem a sabia correr.
    """
    await recuperar_tarefas_perdidas()

    agora = _agora()
    filtro: dict[str, Any] = {
        "status": ESTADO_PENDENTE,
        "disponivel_em": {"$lte": _iso(agora)},
    }
    if tipos is not None:
        filtro["type"] = {"$in": list(tipos)}
    elif excluir_tipos is not None:
        filtro["type"] = {"$nin": list(excluir_tipos)}

    try:
        return await db[COLECCAO].find_one_and_update(
            filtro,
            {"$set": {
                "status": ESTADO_A_PROCESSAR,
                "started_at": _iso(agora),
                "updated_at": _iso(agora),
            }},
            sort=[("created_at", 1)],
            projection={"_id": 0},
        )
    except Exception as e:
        logger.warning("[FILA] Falha a reclamar tarefa: %s", e)
        return None


async def complete_task(task_id: str, result: Any = None) -> bool:
    """Marca a tarefa como concluída."""
    agora = _agora()
    try:
        await db[COLECCAO].update_one(
            {"id": task_id},
            {"$set": {
                "status": ESTADO_CONCLUIDA,
                "result": result,
                "error": None,
                "finished_at": _iso(agora),
                # Campo datetime NATIVO: o TTL do Mongo não funciona sobre
                # uma string ISO (a lição do `idx_ttl` descontinuado).
                "finished_at_dt": agora,
                "updated_at": _iso(agora),
            }},
        )
        return True
    except Exception as e:
        logger.warning("[FILA] Falha a concluir %s: %s", task_id, e)
        return False


async def fail_task(task_id: str, error: str = "") -> bool:
    """Registra a falha: volta à fila com espera, ou desiste.

    A espera é o que distingue uma correcção de uma troca de problema:
    sem ela, uma tarefa que falhe sempre voltava de imediato e o
    `worker_loop` — que só dorme quando a fila está vazia — girava a
    100% de CPU.
    """
    agora = _agora()
    try:
        tarefa = await db[COLECCAO].find_one({"id": task_id}, {"_id": 0})
    except Exception as e:
        logger.warning("[FILA] Falha a ler %s para marcar erro: %s", task_id, e)
        return False
    if not tarefa:
        return False

    tentativas = int(tarefa.get("tentativas") or 0) + 1
    maximo = int(tarefa.get("max_tentativas") or MAX_TENTATIVAS)
    desistir = tentativas >= maximo

    actualizacao: dict[str, Any] = {
        "tentativas": tentativas,
        "error": str(error)[:2000],
        "updated_at": _iso(agora),
    }
    if desistir:
        actualizacao["status"] = ESTADO_FALHADA
        actualizacao["finished_at"] = _iso(agora)
        actualizacao["finished_at_dt"] = agora
        logger.error(
            "[FILA] Tarefa %s (%s) falhada após %s tentativas: %s",
            task_id, tarefa.get("type"), tentativas, str(error)[:200],
        )
    else:
        espera = espera_da_tentativa(tentativas)
        actualizacao["status"] = ESTADO_PENDENTE
        actualizacao["disponivel_em"] = _iso(agora + timedelta(seconds=espera))
        actualizacao["started_at"] = None
        logger.warning(
            "[FILA] Tarefa %s (%s) falhou (%s/%s), repete em %ss: %s",
            task_id, tarefa.get("type"), tentativas, maximo, espera, str(error)[:200],
        )

    try:
        await db[COLECCAO].update_one({"id": task_id}, {"$set": actualizacao})
        return True
    except Exception as e:
        logger.warning("[FILA] Falha a gravar o erro de %s: %s", task_id, e)
        return False


# Tipo de tarefa com que o painel pede ao WORKER para correr um job. É a
# ponte entre os dois processos do `render.yaml`: a web não consegue
# invocar o worker, mas os dois vêem esta colecção.
TIPO_FORCAR_JOB = "forcar_job"


async def pedir_execucao_de_job(chave: str) -> Optional[str]:
    """Pede ao worker para correr um job. Idempotente por job.

    Se já houver um pedido à espera para o mesmo job, devolve o id desse
    — carregar duas vezes no botão não enfileira dois ciclos.
    """
    try:
        existente = await db[COLECCAO].find_one(
            {
                "type": TIPO_FORCAR_JOB,
                "payload.chave": chave,
                "status": {"$in": [ESTADO_PENDENTE, ESTADO_A_PROCESSAR]},
            },
            {"_id": 0, "id": 1},
        )
    except Exception as e:
        logger.warning("[FILA] Falha a verificar pedidos de %s: %s", chave, e)
        existente = None
    if existente:
        return existente.get("id")

    # Uma tentativa só: um pedido manual que falhe tem de o DIZER, não
    # repetir-se sozinho às escondidas meia hora depois.
    return await add_task(TIPO_FORCAR_JOB, {"chave": chave}, max_tentativas=1)


async def pedidos_de_execucao_por_job() -> dict[str, dict]:
    """O pedido mais recente por job — para o painel dizer em que pé está.

    É isto que transforma «Nunca correu» num diagnóstico: um pedido que
    ninguém reclama PROVA que o Processador não está a ouvir, em vez de
    deixar a dúvida entre "o job falhou" e "o processo não está lá".
    """
    try:
        pedidos = await db[COLECCAO].find(
            {"type": TIPO_FORCAR_JOB},
            {"_id": 0, "id": 1, "status": 1, "payload": 1, "created_at": 1,
             "finished_at": 1, "error": 1},
        ).sort("created_at", -1).to_list(100)
    except Exception as e:
        logger.warning("[FILA] Falha a ler pedidos de execução: %s", e)
        return {}

    por_job: dict[str, dict] = {}
    for pedido in pedidos:
        chave = (pedido.get("payload") or {}).get("chave")
        if chave and chave not in por_job:
            por_job[chave] = pedido
    return por_job


async def estado_da_fila() -> dict[str, int]:
    """Contagem por estado — para o painel e para o diagnóstico."""
    contagens: dict[str, int] = {}
    for estado in (ESTADO_PENDENTE, ESTADO_A_PROCESSAR, ESTADO_CONCLUIDA, ESTADO_FALHADA):
        try:
            contagens[estado] = await db[COLECCAO].count_documents({"status": estado})
        except Exception:
            contagens[estado] = 0
    return contagens
