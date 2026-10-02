"""
Estado do motor de background — GET /api/automations (Lote 4, ponto 14)
e execução forçada — POST /api/automations/{chave}/executar (Lote 2, ponto 1).

A lista sai do REGISTO DECLARADO (`job_heartbeat.JOBS_DECLARADOS`), não da
colecção: se listássemos só o que bateu, o job mais avariado de todos — o
que nunca arrancou — era o único invisível.

PORQUE É QUE O PAINEL DEIXOU DE SER READ-ONLY
  A objecção registada aqui era: «um disparo manual a partir da web não
  chegaria ao processo worker (são processos distintos do `render.yaml`), e
  um botão que não faz nada é pior do que não existir». A objecção está
  certa, e a fila persistente do Lote 2 é a resposta a ela:

    · job do processo **web** → corre AQUI, no processo que o alberga;
    · job do processo **worker** → fica um PEDIDO na fila que o
      `scheduler_loop` reclama no ciclo seguinte.

  A resposta diz qual dos dois aconteceu. "A correr" e "pedido entregue"
  são estados diferentes, e dar o segundo pelo primeiro seria o botão a
  mentir — exactamente o que a objecção original queria evitar.

E O PEDIDO QUE NINGUÉM RECLAMA É O DIAGNÓSTICO
  Um pedido que fica `pendente` PROVA que o Processador não está a ouvir.
  Deixa de ser preciso adivinhar entre "o job falhou" e "o processo não
  está lá" — a pergunta que o «Nunca correu» deste lote levantou e que
  nenhum dos estados do painel sabia responder.

O que «correr o job» significa vive em `job_executors.EXECUTORES`, não
aqui: uma segunda definição no endpoint divergiria do laço sem dar erro.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from services.job_heartbeat import (
    ESTADO_ATRASADO,
    ESTADO_FALHOU,
    ESTADO_NUNCA_CORREU,
    JOBS_DECLARADOS,
    JOBS_POR_CHAVE,
    estado_do_job,
    job_esta_activo,
    ler_batimentos,
    proxima_execucao,
)

logger = logging.getLogger(__name__)

# Estados que merecem atenção humana. "desactivado" NÃO está aqui: em dev
# quase tudo está desligado de propósito (kill switches por RAM), e um
# painel a gritar vermelho em dev ensina toda a gente a ignorá-lo.
ESTADOS_COM_PROBLEMA = frozenset({ESTADO_FALHOU, ESTADO_ATRASADO, ESTADO_NUNCA_CORREU})


def montar_linha(
    declarado: dict,
    registo: dict | None,
    *,
    agora: datetime,
    pedido: dict | None = None,
) -> dict[str, Any]:
    """Uma linha do painel: o declarado + o observado + o estado derivado."""
    from services.job_executors import motivo_para_nao_forcar, pode_ser_forcado

    estado = estado_do_job(declarado, registo, agora=agora)
    registo = registo or {}
    chave = declarado["chave"]
    activo = job_esta_activo(declarado)
    return {
        # Execução forçada: o botão só aparece quando há mesmo o que
        # carregar. Um job desactivado não se força (em dev quase tudo
        # está desligado por kill switch, e o que se força aí toca em
        # serviços reais), e o CDC não tem ciclo para repetir — o motivo
        # vai à vista, senão o utilizador clica outra vez.
        "pode_forcar": activo and pode_ser_forcado(chave),
        "motivo_sem_forcar": (
            motivo_para_nao_forcar(chave)
            or ("" if activo else "O job está desactivado neste ambiente.")
        ),
        "pedido_pendente": _resumir_pedido(pedido),
        **_campos_observados(declarado, registo, chave, activo, estado, agora=agora),
    }


def _resumir_pedido(pedido: dict | None) -> dict | None:
    """O estado do último pedido de execução forçada deste job."""
    if not pedido:
        return None
    return {
        "estado": pedido.get("status"),
        "pedido_em": pedido.get("created_at"),
        "concluido_em": pedido.get("finished_at"),
        "erro": pedido.get("error"),
    }


def _campos_observados(
    declarado: dict,
    registo: dict,
    chave: str,
    activo: bool,
    estado: str,
    *,
    agora: datetime,
) -> dict[str, Any]:
    return {
        "chave": chave,
        "nome": declarado["nome"],
        "descricao": declarado.get("descricao", ""),
        "processo": declarado["processo"],
        "interval_seconds": declarado["interval_seconds"],
        "activo": activo,
        "estado": estado,
        "ultima_execucao": registo.get("finished_at"),
        "ultimo_inicio": registo.get("started_at"),
        "proxima_execucao": proxima_execucao(declarado, registo or None),
        "duracao_ms": registo.get("duration_ms"),
        "erro": registo.get("error"),
        "run_count": registo.get("run_count", 0),
        "failure_count": registo.get("failure_count", 0),
        # Com dois processos e dois workers uvicorn, saber QUEM bateu é
        # metade do diagnóstico.
        "host": registo.get("host"),
        "pid": registo.get("pid"),
    }


def resumir(linhas: list[dict]) -> dict[str, Any]:
    """Contagens para o cabeçalho do painel."""
    com_problema = [l for l in linhas if l["estado"] in ESTADOS_COM_PROBLEMA]
    return {
        "total": len(linhas),
        "com_problema": len(com_problema),
        "desactivados": sum(1 for l in linhas if not l["activo"]),
        "saudaveis": sum(
            1 for l in linhas
            if l["activo"] and l["estado"] not in ESTADOS_COM_PROBLEMA
        ),
    }


async def run_get_automations_status() -> dict[str, Any]:
    """GET /api/automations — sinais vitais do motor de background."""
    from services.task_queue_mongo import estado_da_fila, pedidos_de_execucao_por_job

    agora = datetime.now(timezone.utc)
    batimentos = await ler_batimentos()
    pedidos = await pedidos_de_execucao_por_job()

    linhas = [
        montar_linha(
            declarado,
            batimentos.get(declarado["chave"]),
            agora=agora,
            pedido=pedidos.get(declarado["chave"]),
        )
        for declarado in JOBS_DECLARADOS
    ]

    return {
        "jobs": linhas,
        "resumo": resumir(linhas),
        # O estado da fila responde à pergunta que os batimentos não
        # respondem: o Processador está a CONSUMIR? Tarefas pendentes a
        # acumular com zero concluídas é um worker que não está a ouvir.
        "fila": await estado_da_fila(),
        "gerado_em": agora.isoformat(),
    }


async def run_forcar_execucao_de_job(chave: str, user: dict | None = None) -> dict[str, Any]:
    """POST /api/automations/{chave}/executar — correr um job agora.

    Dois caminhos, porque o motor vive em dois processos e um não invoca o
    outro. A resposta diz qual deles aconteceu — dar "pedido entregue" por
    "a correr" seria o botão a mentir.
    """
    from services.job_executors import PROCESSO_WORKER, executar_job, pode_ser_forcado
    from services.task_queue_mongo import pedir_execucao_de_job

    declarado = JOBS_POR_CHAVE.get(chave)
    if not declarado:
        raise HTTPException(status_code=404, detail=f"Job desconhecido: {chave}")

    if not job_esta_activo(declarado):
        # 409 e não 403: não é falta de permissão, é o job estar desligado
        # neste ambiente. Em dev quase tudo está, de propósito.
        raise HTTPException(
            status_code=409,
            detail=f"O job '{declarado['nome']}' está desactivado neste ambiente.",
        )

    if not pode_ser_forcado(chave):
        from services.job_executors import motivo_para_nao_forcar

        raise HTTPException(
            status_code=409,
            detail=motivo_para_nao_forcar(chave) or "Este job não pode ser forçado.",
        )

    quem = (user or {}).get("email") or "desconhecido"

    if declarado.get("processo") == PROCESSO_WORKER:
        pedido_id = await pedir_execucao_de_job(chave)
        if not pedido_id:
            raise HTTPException(
                status_code=503,
                detail="Não foi possível registar o pedido — fila indisponível.",
            )
        logger.info("[MOTOR] %s pediu execução de %s (worker)", quem, chave)
        return {
            "success": True,
            "modo": "pedido_ao_worker",
            "pedido_id": pedido_id,
            "mensagem": (
                f"Pedido entregue ao Processador. «{declarado['nome']}» arranca "
                "no próximo ciclo (até 1 minuto). Se ficar pendente, o "
                "Processador não está a consumir a fila."
            ),
        }

    # Processo web: estamos no processo que alberga o job.
    logger.info("[MOTOR] %s forçou execução de %s (web)", quem, chave)
    try:
        await executar_job(chave)
    except Exception as e:
        # O batimento já registou `erro`; aqui diz-se a quem carregou.
        logger.error("[MOTOR] Execução forçada de %s falhou: %s", chave, e)
        raise HTTPException(
            status_code=500,
            detail=f"«{declarado['nome']}» falhou: {str(e)[:300]}",
        )

    return {
        "success": True,
        "modo": "executado_agora",
        "mensagem": f"«{declarado['nome']}» correu agora.",
    }
