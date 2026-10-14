"""Ciclo de vida dos jobs de recolha no Estado (`portal_scraper_jobs`).

Três lacunas que este módulo fecha (Bloco 5, pontos 8 e 9):

* **Jobs presos para sempre.** O estado vive na base de dados, a execução
  vive num `BackgroundTask` do processo web. Se o contentor reinicia a meio —
  um deploy no Render chega — o job fica em `processing` ou `awaiting_mfa` para
  sempre e o ecrã do cliente fica a girar sem fim (o `beforeunload` do diálogo
  ainda lhe impede de fechar o separador). Um job activo mais velho do que o
  orçamento máximo de uma execução está morto: marca-se como erro, com
  mensagem, na primeira leitura ou criação que lhe toque.
* **Dois pedidos em simultâneo no mesmo processo.** O código MFA vive numa
  chave por PROCESSO (`mfa_code:{process_id}`) e o segundo clique no botão
  disparava um segundo login — outro SMS ao cliente, e o código que ele
  escreveu servia o scraper errado. Há um job activo por processo.
* **O estado devolvido a quem quer que tenha o id.** `GET /scraper-job/{id}`
  não exigia autenticação e devolvia o documento inteiro — incluindo o
  `mfa_code` em claro quando o Redis falha e o código vive no Mongo. Hoje há
  posse (404 igual para alheio e inexistente) e uma projecção fechada.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from database import db
from services.gov_fetch_policy import (
    ESPERA_PELO_SEMAFORO_SEGUNDOS,
    ORCAMENTO_TOTAL_SEGUNDOS,
    orcamento_da_tentativa,
)
from services.mfa_cache import ESTADOS_ACTIVOS

logger = logging.getLogger(__name__)

# Uma execução não vive mais do que a fila + o orçamento total (+ folga).
# Acima disto o job é um cadáver, não uma execução lenta.
IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS = (
    ESPERA_PELO_SEMAFORO_SEGUNDOS + ORCAMENTO_TOTAL_SEGUNDOS + orcamento_da_tentativa()
)

MENSAGEM_DE_JOB_MORTO = (
    "A obtenção automática foi interrompida. Tente novamente ou envie os "
    "documentos através do botão de upload."
)

# O que o ecrã do cliente pode ler de um job. Fechado: um campo novo no job
# não chega ao cliente sem alguém o decidir (é assim que o `mfa_code` evitaria
# sair), e `process_id` não precisa de voltar a quem já o tem.
CAMPOS_PUBLICOS_DO_JOB = (
    "id", "source", "status", "documents_count", "documents_missing",
    "error_type", "message", "created_at", "updated_at",
)


#: Booleano que existe SÓ enquanto o job está activo. O índice único parcial
#: `idx_scraper_job_activo_unico` (`process_id`, filtro `active: True`) é o que torna «um job
#: activo por processo» ATÓMICO (D-29): o `partialFilterExpression` do Mongo não aceita `$in`
#: sobre `status`, daí um campo próprio. Tem de ser desligado em TODA a saída de um estado
#: activo — um `active: True` esquecido bloquearia o processo para sempre.
CAMPO_ACTIVO = "active"


class JobJaActivo(Exception):
    """Já existe um job activo para o processo (perdeu-se a corrida da criação)."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _limite_de_idade(agora: Optional[datetime] = None) -> str:
    return ((agora or _agora()) - timedelta(seconds=IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS)).isoformat()


async def encerrar_jobs_mortos(process_id: Optional[str] = None, *, agora: Optional[datetime] = None) -> int:
    """Marca como erro os jobs activos que já ultrapassaram o tempo máximo.

    Devolve quantos encerrou. Nunca levanta: é uma limpeza oportunista a
    correr dentro de um pedido do cliente.
    """
    filtro: dict = {
        "status": {"$in": list(ESTADOS_ACTIVOS)},
        "created_at": {"$lt": _limite_de_idade(agora)},
    }
    if process_id:
        filtro["process_id"] = process_id
    try:
        resultado = await db.portal_scraper_jobs.update_many(
            filtro,
            {
                "$set": {
                    "status": "error",
                    "error_type": "scraper_unavailable",
                    "message": MENSAGEM_DE_JOB_MORTO,
                    "updated_at": (agora or _agora()).isoformat(),
                    CAMPO_ACTIVO: False,
                },
                "$unset": {"mfa_code": ""},
            },
        )
    except Exception as exc:
        logger.warning("[GOV-JOBS] Não foi possível encerrar jobs mortos: %s", type(exc).__name__)
        return 0
    encerrados = getattr(resultado, "modified_count", 0) or 0
    if encerrados:
        logger.warning(
            "[GOV-JOBS] %d job(s) de recolha encerrado(s) por excederem %ss%s.",
            encerrados, IDADE_MAXIMA_DE_UM_JOB_SEGUNDOS,
            f" (processo {process_id})" if process_id else "",
        )
    return encerrados


async def job_activo_do_processo(process_id: str) -> Optional[dict]:
    """O job activo (mais recente) do processo, depois de limpar os mortos."""
    await encerrar_jobs_mortos(process_id)
    job = await db.portal_scraper_jobs.find_one(
        {"process_id": process_id, "status": {"$in": list(ESTADOS_ACTIVOS)}},
        {"_id": 0, "mfa_code": 0},
        sort=[("created_at", -1)],
    )
    # A projecção da consulta poupa a transferência; a garantia de que o código
    # não sai é esta, que não depende de a base de dados a aplicar.
    return projeccao_publica(job) if job else None


async def criar_job(process_id: str, source: str) -> str:
    """Cria o job em `processing` e devolve o id.

    ATÓMICO (D-29): o índice único parcial recusa um segundo job activo para o mesmo processo, e a
    corrida perde com ``JobJaActivo`` — verificar «há um activo?» e depois criar eram duas operações,
    e dois pedidos simultâneos passavam ambos (dois logins, dois SMS ao cliente).
    """
    job_id = str(uuid.uuid4())
    agora = _agora().isoformat()
    try:
        await db.portal_scraper_jobs.insert_one({
            "id": job_id,
            "process_id": process_id,
            "source": source,
            "status": "processing",
            CAMPO_ACTIVO: True,
            "created_at": agora,
            "updated_at": agora,
        })
    except DuplicateKeyError as exc:
        raise JobJaActivo(process_id) from exc
    return job_id


def projeccao_publica(job: dict) -> dict:
    """Só os campos que o ecrã do cliente tem direito a ler."""
    return {campo: job[campo] for campo in CAMPOS_PUBLICOS_DO_JOB if campo in job}


async def ler_job_do_processo(job_id: str, process_id: str) -> Optional[dict]:
    """O job, se existir E for deste processo; `None` caso contrário.

    `None` serve os dois casos de propósito: o chamador responde 404 igual para
    «não existe» e «não é teu», senão o endpoint confirma ids a quem adivinha.
    """
    await encerrar_jobs_mortos(process_id)
    job = await db.portal_scraper_jobs.find_one({"id": job_id, "process_id": process_id}, {"_id": 0})
    return projeccao_publica(job) if job else None
